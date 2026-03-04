"""
sentinel_agent.rpc.consumer
=============================
oslo.messaging RPC endpoint for sentinel-agent.

The agent exposes exactly ONE RPC method: ``execute_payload``.
This minimal surface area is intentional — the agent should do
as little as possible beyond receiving, verifying and executing.

Security sequence (MUST NOT be modified or reordered):
  1. ``PayloadVerifier.verify()``  — RSA-SHA256 + timestamp freshness.
  2. Parse into ``ExecutionPayload`` Pydantic model.
  3. Check driver is in ``conf.agent.enabled_drivers`` whitelist.
  4. Load driver via stevedore.
  5. ``driver.validate_args()``    — second args check (defence in depth).
  6. ``driver.execute()``          — subprocess, NO shell=True.
  7. Return ``ExecutionResult`` as dict.
"""

import logging
import time
from typing import Any

import oslo_messaging
from stevedore import driver as stevedore_driver

from common.exceptions import DriverNotFound, SignatureVerificationFailed
from common.schemas.payload import ExecutionPayload
from sentinel_agent.crypto import PayloadVerifier

LOG = logging.getLogger(__name__)


class AgentRPCEndpoint:
    """
    Single-method oslo.messaging endpoint for sentinel-agent.

    The ``target`` attribute declares the minimum server-side RPC version.
    oslo.messaging will refuse calls from clients requesting a higher version.
    """

    target = oslo_messaging.Target(version="1.0")

    def __init__(self, conf, verifier: PayloadVerifier, conductor_client) -> None:
        """
        Args:
            conf:              oslo.config CONF (with [agent] group registered).
            verifier:          Initialised ``PayloadVerifier`` with conductor's public key.
            conductor_client:  oslo.messaging RPC client for casting results back.
        """
        self._conf = conf
        self._verifier = verifier
        self._conductor = conductor_client
        # Simple in-memory driver cache — drivers are stateless so reuse is safe
        self._driver_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # The only exposed RPC method
    # ------------------------------------------------------------------

    def execute_payload(self, ctxt: dict, payload: dict) -> dict:
        """
        Receive, verify and execute a signed execution payload.

        This method is called by oslo.messaging when a message arrives
        on the agent's dedicated queue (``sentinel.agent.<agent_id>``).

        Returns a result dict — oslo.messaging sends it back as the RPC reply.
        """
        message_id = payload.get("message_id", "unknown")

        # STEP 1 — Cryptographic verification (GOLDEN RULE: never skip)
        try:
            self._verifier.verify(payload)
        except SignatureVerificationFailed as exc:
            LOG.critical(
                "SECURITY ALERT: Rejected payload message_id=%s — %s",
                message_id, exc,
            )
            # ACK the message (remove from queue) but do NOT execute
            return {
                "status": "rejected",
                "message_id": message_id,
                "reason": "signature_verification_failed",
            }

        # STEP 2 — Parse into typed Pydantic model
        try:
            exec_payload = ExecutionPayload(**payload)
        except Exception as exc:
            LOG.error("Malformed payload message_id=%s: %s", message_id, exc)
            return {
                "status": "error",
                "message_id": message_id,
                "reason": f"payload_parse_error: {exc}",
            }

        driver_name = exec_payload.execution.driver
        command = exec_payload.execution.command
        args = exec_payload.execution.args
        allowed_paths = exec_payload.execution.allowed_paths
        require_sudo = exec_payload.execution.require_sudo

        # STEP 3 — Load driver (also checks the enabled_drivers whitelist)
        try:
            driver = self._get_driver(driver_name)
        except DriverNotFound as exc:
            LOG.error(
                "Driver not available message_id=%s driver=%r: %s",
                message_id, driver_name, exc,
            )
            return {
                "status": "error",
                "message_id": message_id,
                "reason": f"driver_not_found: {driver_name}",
            }

        # STEP 4 — Args validation (defence in depth — conductor already validated)
        # args_regex is not re-sent in the payload (policy-side info); allowed_paths IS
        # sent because it must be enforced by the driver and is included in the signature.
        try:
            driver.validate_args(command, args, args_regex=None, allowed_paths=allowed_paths)
        except Exception as exc:
            LOG.warning(
                "Args validation failed message_id=%s: %s", message_id, exc
            )
            return {
                "status": "error",
                "message_id": message_id,
                "reason": f"args_validation_failed: {exc}",
            }

        # STEP 5 — Execute
        request_id = exec_payload.context.request_id
        LOG.info(
            "Executing message_id=%s request_id=%s driver=%r command=%r args=%r sudo=%s",
            message_id, request_id, driver_name, command, args, require_sudo,
        )
        t0 = time.monotonic()
        try:
            result = driver.execute(
                command,
                args,
                exec_payload.execution.env,
                exec_payload.execution.limits,
                allowed_paths=allowed_paths,
                require_sudo=require_sudo,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            LOG.error("Execution failed message_id=%s: %s", message_id, exc)
            self._report_result(request_id, 1, "", str(exc), duration_ms)
            return {
                "status": "error",
                "message_id": message_id,
                "reason": str(exc),
            }

        duration_ms = int((time.monotonic() - t0) * 1000)
        LOG.info(
            "Execution complete message_id=%s exit_code=%d duration_ms=%d truncated=%s",
            message_id, result.exit_code, duration_ms, result.truncated,
        )
        self._report_result(
            request_id, result.exit_code, result.stdout, result.stderr, duration_ms
        )
        return {
            "status": "completed",
            "message_id": message_id,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "truncated": result.truncated,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _report_result(
        self,
        request_id: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> None:
        """Cast execution result back to sentinel-conductor (fire-and-forget)."""
        try:
            self._conductor.cast(
                {},
                "report_execution_result",
                request_id=request_id,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            # Non-fatal — log and continue. The audit log will remain in
            # 'success' (dispatched) state without output data.
            LOG.error(
                "Failed to report execution result for request_id=%s: %s",
                request_id, exc,
            )

    def _get_driver(self, driver_name: str) -> Any:
        """
        Return a cached driver instance, loading it via stevedore if needed.

        Raises:
            DriverNotFound: if the driver is not in ``enabled_drivers``
                            or not registered as an entry point.
        """
        if driver_name in self._driver_cache:
            return self._driver_cache[driver_name]

        allowed = list(self._conf.agent.enabled_drivers)
        if driver_name not in allowed:
            raise DriverNotFound(
                f"Driver {driver_name!r} is not in the allowed drivers list: {allowed}"
            )

        try:
            mgr = stevedore_driver.DriverManager(
                namespace="sentinel.agent.drivers",
                name=driver_name,
                invoke_on_load=True,
            )
            driver = mgr.driver
        except Exception as exc:
            raise DriverNotFound(
                f"Could not load driver {driver_name!r} via stevedore: {exc}"
            ) from exc

        self._driver_cache[driver_name] = driver
        LOG.info("Driver loaded and cached: %r", driver_name)
        return driver
