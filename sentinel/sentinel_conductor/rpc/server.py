"""
sentinel_conductor.rpc.server
===============================
oslo.messaging RPC endpoint for sentinel-conductor.

Execution flow
--------------
  mcp-api / admin-api
       │
       │  RPC call: request_execution(request_dict)
       ▼
  ConductorRPCEndpoint.request_execution()
       │
       ├─ [RBAC engine] ──────────────────── DENY → AuditLog(DENIED) + return error
       │
       ├─ require_2fa = False
       │       └─ sign_and_dispatch() → call scheduler.dispatch() → cast to target
       │               └─ AuditLog(SUCCESS) + return {"status": "dispatched"}
       │
       └─ require_2fa = True
               ├─ issue_challenge() via 2FA provider plugin
               ├─ TwoFAChallenge(PENDING) persisted to DB
               ├─ Background thread: _TwoFAPoller started
               └─ return {"status": "pending_2fa", "challenge_id": ...}

                           _TwoFAPoller (daemon thread)
                                  │ polls verify_challenge() every N seconds
                                  ├─ APPROVED → sign_and_dispatch() → AuditLog(SUCCESS)
                                  ├─ REJECTED → AuditLog(DENIED)
                                  └─ EXPIRED  → AuditLog(FAILURE)
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import oslo_messaging

from common.crypto import sign_payload
from common.exceptions import TargetUnreachable, PolicyDenied, SentinelException
from common.messaging.rpc import get_rpc_client
from common.messaging.transport import get_transport
from common.models import AuditLog, AuditOutcome, ChallengeStatus, TwoFAChallenge
from common.schemas.requests import ExecutionRequest
from sentinel_conductor.auth.base import ChallengeContext
from sentinel_conductor.rbac.engine import AuthorizationResult, RBACEngine
from sentinel_conductor.rpc.crud import ConductorCRUDMixin

LOG = logging.getLogger(__name__)


class ConductorRPCEndpoint(ConductorCRUDMixin):
    """
    oslo.messaging RPC endpoint — exposes conductor methods to other services.

    All public methods here become callable via oslo.messaging RPC.
    """

    target = oslo_messaging.Target(version="1.0")

    def __init__(
        self,
        conf,
        session_factory: Callable,
        private_key,
        auth_provider,
    ) -> None:
        """
        Args:
            conf:             oslo.config CONF (fully parsed).
            session_factory:  ``sentinel_conductor.db.get_session`` context manager.
            private_key:      Loaded RSA private key (``RSAPrivateKey``).
            auth_provider:    Loaded 2FA provider (``BaseAuthProvider`` instance).
        """
        self._conf = conf
        self._session_factory = session_factory
        self._private_key = private_key
        self._auth_provider = auth_provider
        self._scheduler_client = None
        self._scheduler_client_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Scheduler client (lazy init — scheduler may start after conductor)
    # ------------------------------------------------------------------

    def _get_scheduler_client(self):
        if self._scheduler_client is not None:
            return self._scheduler_client
        with self._scheduler_client_lock:
            if self._scheduler_client is None:
                self._scheduler_client = get_rpc_client(
                    get_transport(self._conf),
                    topic=self._conf.messaging.rpc_topic_scheduler,
                    timeout=self._conf.messaging.rpc_timeout,
                )
        return self._scheduler_client

    # ------------------------------------------------------------------
    # Public RPC methods
    # ------------------------------------------------------------------

    def request_execution(self, ctxt: dict, request: dict) -> dict:
        """
        Evaluate an execution request and either dispatch it or initiate 2FA.

        Args:
            ctxt:    oslo.messaging request context (passed automatically).
            request: Serialised ``ExecutionRequest`` as a plain dict.

        Returns:
            One of:
            - ``{"status": "dispatched",   "message_id": str, "request_id": str}``
            - ``{"status": "pending_2fa",  "challenge_id": str, "request_id": str}``
            - ``{"status": "denied",       "reason": str, "request_id": str}``
            - ``{"status": "error",        "reason": str}``
        """
        try:
            exec_request = ExecutionRequest(**request)
        except Exception as exc:
            LOG.error("Invalid execution request payload: %s", exc)
            return {"status": "error", "reason": f"Invalid request payload: {exc}"}

        # ----------------------------------------------------------
        # Transaction 1: INSERT audit log + RBAC check, then commit.
        # The commit happens BEFORE dispatching to the target so that
        # report_execution_result (which may arrive within milliseconds
        # on fast targets) can always find the audit log row.
        # ----------------------------------------------------------
        with self._session_factory() as session:
            audit = AuditLog(
                initiator_id=exec_request.initiator_id,
                action=f"execute:{exec_request.command}",
                target_id=exec_request.target_id,
                driver=exec_request.driver,
                binary=exec_request.command,
                args=" ".join(exec_request.args),
                outcome=AuditOutcome.PENDING,
                request_id=exec_request.request_id,
            )
            session.add(audit)
            session.flush()
            audit_id = audit.id

            # RBAC evaluation
            try:
                auth_result = RBACEngine(session).authorize(exec_request)
            except PolicyDenied as exc:
                audit.outcome = AuditOutcome.DENIED
                audit.reason = str(exc)
                LOG.warning(
                    "DENIED request_id=%s: %s", exec_request.request_id, exc
                )
                return {
                    "status": "denied",
                    "reason": str(exc),
                    "request_id": exec_request.request_id,
                }

            audit.twofa_required = auth_result.requires_2fa

            # Path A: 2FA required (stays inside this transaction)
            if auth_result.requires_2fa:
                return self._handle_2fa_required(
                    session, exec_request, auth_result, audit
                )
        # ← Transaction 1 committed here — audit log visible to all queries

        # ----------------------------------------------------------
        # Path B: No 2FA — dispatch outside any open transaction so
        # that the target's report_execution_result can update the row.
        # ----------------------------------------------------------
        try:
            message_id = self._sign_and_dispatch(exec_request, auth_result)
        except TargetUnreachable as exc:
            with self._session_factory() as session:
                failed_audit = session.get(AuditLog, audit_id)
                if failed_audit:
                    failed_audit.outcome = AuditOutcome.FAILURE
                    failed_audit.reason = str(exc)
            LOG.warning(
                "Target unreachable request_id=%s: %s",
                exec_request.request_id, exc,
            )
            return {
                "status": "target_unreachable",
                "reason": str(exc),
                "request_id": exec_request.request_id,
            }

        # Transaction 2: persist message_id. Only set outcome=SUCCESS if
        # report_execution_result hasn't already resolved it (fast targets).
        with self._session_factory() as session:
            dispatched_audit = session.get(AuditLog, audit_id)
            if dispatched_audit:
                dispatched_audit.message_id = message_id
                if dispatched_audit.outcome == AuditOutcome.PENDING:
                    dispatched_audit.outcome = AuditOutcome.SUCCESS

        LOG.info(
            "Dispatched request_id=%s message_id=%s target=%s",
            exec_request.request_id, message_id, exec_request.target_id,
        )
        return {
            "status": "dispatched",
            "message_id": message_id,
            "request_id": exec_request.request_id,
        }

    def get_audit_log(self, ctxt: dict, request_id: str) -> dict | None:
        """Retrieve an audit log entry by request_id (for polling status)."""
        from sqlalchemy import select

        with self._session_factory() as session:
            audit: AuditLog | None = session.scalar(
                select(AuditLog).where(AuditLog.request_id == request_id)
            )
            if audit is None:
                return None
            return {
                "id": str(audit.id),
                "request_id": audit.request_id,
                "outcome": audit.outcome.value,
                "action": audit.action,
                "target_id": audit.target_id,
                "message_id": audit.message_id,
                "reason": audit.reason,
                "event_time": audit.event_time.isoformat(),
                "twofa_required": audit.twofa_required,
                "stdout": audit.stdout,
                "stderr": audit.stderr,
                "exit_code": audit.exit_code,
                "duration_ms": audit.duration_ms,
            }

    def report_execution_result(
        self,
        ctxt: dict,
        request_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> None:
        """
        Receive command execution output from a sentinel-target.

        Called via oslo.messaging cast (fire-and-forget) by the target
        after a command completes.  Updates the audit log with the output
        and finalises the outcome based on exit_code.
        """
        from sqlalchemy import select

        with self._session_factory() as session:
            audit: AuditLog | None = session.scalar(
                select(AuditLog).where(AuditLog.request_id == request_id)
            )
            if audit is None:
                LOG.warning(
                    "report_execution_result: no audit log found for request_id=%r",
                    request_id,
                )
                return

            audit.stdout = stdout
            audit.stderr = stderr
            audit.exit_code = exit_code
            audit.duration_ms = duration_ms
            audit.outcome = AuditOutcome.SUCCESS if exit_code == 0 else AuditOutcome.FAILURE

            LOG.info(
                "Execution result recorded: request_id=%s exit_code=%d duration_ms=%d",
                request_id, exit_code, duration_ms,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_2fa_required(
        self,
        session,
        exec_request: ExecutionRequest,
        auth_result: AuthorizationResult,
        audit: AuditLog,
    ) -> dict:
        """Create a 2FA challenge and start a background polling thread."""
        context = ChallengeContext(
            initiator_id=exec_request.initiator_id,
            target_agent_id=exec_request.target_id,
            command=exec_request.command,
            args=exec_request.args,
            request_id=exec_request.request_id,
        )

        # Issue the challenge (send push notification)
        loop = asyncio.new_event_loop()
        try:
            challenge_response = loop.run_until_complete(
                self._auth_provider.issue_challenge(context)
            )
        finally:
            loop.close()

        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self._conf.conductor.twofa_challenge_timeout_seconds
        )
        challenge_record = TwoFAChallenge(
            id=challenge_response.challenge_id,   # sync DB PK with provider's in-memory key
            audit_log_id=audit.id,
            provider=self._conf.auth.provider,
            status=ChallengeStatus.PENDING,
            context_json=json.dumps({
                "initiator_id": exec_request.initiator_id,
                "command": exec_request.command,
                "args": exec_request.args,
            }),
            external_ref=challenge_response.external_ref,
            expires_at=expires_at,
        )
        session.add(challenge_record)
        session.flush()
        challenge_id = challenge_record.id

        audit.twofa_provider = self._conf.auth.provider
        audit.twofa_challenge_id = challenge_id
        audit.outcome = AuditOutcome.PENDING

        # Start background poller daemon thread
        poller = _TwoFAPoller(
            conf=self._conf,
            session_factory=self._session_factory,
            auth_provider=self._auth_provider,
            exec_request=exec_request,
            auth_result=auth_result,
            audit_id=audit.id,
            challenge_id=challenge_id,
            external_ref=challenge_response.external_ref,
            sign_and_dispatch_fn=self._sign_and_dispatch,
        )
        t = threading.Thread(target=poller.run, daemon=True, name=f"2fa-{challenge_id[:8]}")
        t.start()

        LOG.info(
            "2FA challenge issued: request_id=%s challenge_id=%s provider=%s",
            exec_request.request_id, challenge_id, self._conf.auth.provider,
        )
        return {
            "status": "pending_2fa",
            "challenge_id": challenge_id,
            "request_id": exec_request.request_id,
        }

    def _sign_and_dispatch(
        self, exec_request: ExecutionRequest, auth_result: AuthorizationResult
    ) -> str:
        """
        Build, sign the payload and route it through sentinel-scheduler.

        The scheduler performs a target liveness check before casting
        the payload to ``sentinel.target.<target_id>``.

        Returns the message_id of the dispatched payload.

        Raises:
            TargetUnreachable: if the scheduler reports the target is not alive.
        """
        message_id = str(uuid.uuid4())
        timestamp = int(datetime.now(timezone.utc).timestamp())

        payload_dict: dict[str, Any] = {
            "message_id": message_id,
            "context": {
                "initiator_id": exec_request.initiator_id,
                "request_id": exec_request.request_id,
                "twofa_verified": auth_result.requires_2fa,
                "twofa_provider_used": (
                    self._conf.auth.provider if auth_result.requires_2fa else None
                ),
            },
            "execution": {
                "driver": exec_request.driver,
                "command": exec_request.command,
                "args": exec_request.args,
                "env": exec_request.env,
                "limits": {
                    "timeout_seconds": exec_request.timeout_seconds,
                    "max_stdout_bytes": 1_048_576,
                    "max_stderr_bytes": 65_536,
                },
                "allowed_paths": auth_result.command.allowed_paths,
                "require_sudo": auth_result.command.require_sudo,
            },
            "security": {
                "signature": "",   # placeholder — excluded from signing
                "timestamp": timestamp,
                "key_id": None,
            },
        }

        # Sign the fully-built payload (signature field is excluded from signing)
        payload_dict["security"]["signature"] = sign_payload(
            payload_dict, self._private_key
        )

        # Route through scheduler (liveness check + actual queue dispatch)
        result = self._get_scheduler_client().call(
            {},
            "dispatch",
            payload=payload_dict,
            target_id=exec_request.target_id,
        )

        if result.get("status") != "queued":
            raise TargetUnreachable(
                result.get("reason", f"Scheduler rejected dispatch for target {exec_request.target_id!r}")
            )

        return message_id


class _TwoFAPoller:
    """
    Background daemon thread that polls a 2FA provider and dispatches
    the payload once the human approver responds.
    """

    def __init__(
        self,
        conf,
        session_factory,
        auth_provider,
        exec_request: ExecutionRequest,
        auth_result: AuthorizationResult,
        audit_id: str,
        challenge_id: str,
        external_ref: str | None,
        sign_and_dispatch_fn: Callable,
    ) -> None:
        self._conf = conf
        self._session_factory = session_factory
        self._auth_provider = auth_provider
        self._exec_request = exec_request
        self._auth_result = auth_result
        self._audit_id = audit_id
        self._challenge_id = challenge_id
        self._external_ref = external_ref
        self._dispatch = sign_and_dispatch_fn

        # Poll interval — use telegram config if available, else 5s
        try:
            self._poll_interval = conf.telegram.polling_interval_seconds
        except Exception:
            self._poll_interval = 5

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            self._poll_loop(loop)
        finally:
            loop.close()

    def _poll_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        while True:
            time.sleep(self._poll_interval)

            with self._session_factory() as session:
                challenge: TwoFAChallenge | None = session.get(
                    TwoFAChallenge, self._challenge_id
                )
                if challenge is None:
                    LOG.error("2FA challenge %s not found in DB", self._challenge_id)
                    return

                # Already resolved externally (e.g. via webhook)
                if challenge.status != ChallengeStatus.PENDING:
                    if challenge.status == ChallengeStatus.APPROVED:
                        self._dispatch_and_update_audit(session)
                    return

                # Check expiry
                if datetime.now(timezone.utc) > challenge.expires_at:
                    challenge.status = ChallengeStatus.EXPIRED
                    self._update_audit(session, AuditOutcome.FAILURE, "2FA challenge expired")
                    LOG.warning("2FA challenge %s expired", self._challenge_id)
                    return

                # Poll the provider
                try:
                    response = loop.run_until_complete(
                        self._auth_provider.verify_challenge(
                            self._challenge_id, self._external_ref
                        )
                    )
                except Exception as exc:
                    LOG.error(
                        "Error polling 2FA provider for challenge %s: %s",
                        self._challenge_id, exc,
                    )
                    continue  # Retry on next tick

                if response.status == ChallengeStatus.APPROVED:
                    challenge.status = ChallengeStatus.APPROVED
                    challenge.resolved_at = datetime.now(timezone.utc)
                    self._dispatch_and_update_audit(session)
                    return

                elif response.status == ChallengeStatus.REJECTED:
                    challenge.status = ChallengeStatus.REJECTED
                    challenge.resolved_at = datetime.now(timezone.utc)
                    self._update_audit(
                        session, AuditOutcome.DENIED, "2FA rejected by approver"
                    )
                    LOG.info("2FA challenge %s rejected", self._challenge_id)
                    return

    def _dispatch_and_update_audit(self, session) -> None:
        try:
            message_id = self._dispatch(self._exec_request, self._auth_result)
        except TargetUnreachable as exc:
            self._update_audit(
                session,
                AuditOutcome.FAILURE,
                f"Target unreachable after 2FA approval: {exc}",
            )
            LOG.warning(
                "Target unreachable after 2FA approval: challenge=%s — %s",
                self._challenge_id, exc,
            )
            return
        self._update_audit(session, AuditOutcome.SUCCESS, None, message_id=message_id)
        LOG.info(
            "Dispatched after 2FA approval: challenge=%s message_id=%s",
            self._challenge_id, message_id,
        )

    def _update_audit(
        self,
        session,
        outcome: AuditOutcome,
        reason: str | None,
        *,
        message_id: str | None = None,
    ) -> None:
        audit: AuditLog | None = session.get(AuditLog, self._audit_id)
        if audit is not None:
            audit.outcome = outcome
            if reason:
                audit.reason = reason
            if message_id:
                audit.message_id = message_id
