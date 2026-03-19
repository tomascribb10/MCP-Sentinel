"""
sentinel_scheduler.main
========================
Service entry point and RPC endpoint for sentinel-scheduler.

Responsibilities
----------------
1. **Heartbeat reception**: receives ``target_heartbeat`` casts from all
   sentinel-target daemons and maintains an in-memory liveness registry.

2. **DB persistence**: after each heartbeat, calls
   ``conductor.update_target_status()`` via RPC so the conductor can
   persist target state to the central DB (conductor is the only component
   with DB access).

3. **Execution routing**: receives ``dispatch`` calls from the conductor
   (after RBAC + signing), performs a target liveness check, and casts
   the signed payload to the target's dedicated queue
   ``sentinel.target.<target_id>``.

Message flow
------------
  Target  ──cast──►  Scheduler.target_heartbeat()
                         └─ registry.update()
                         └─ conductor.update_target_status()  [cast, non-blocking]

  Conductor  ──call──►  Scheduler.dispatch(payload, target_id)
                             └─ registry.is_alive(target_id) ?
                             │      YES → cast to sentinel.target.<target_id>
                             │             return {"status": "queued"}
                             └─────── NO  → return {"status": "target_unreachable"}
"""

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import oslo_messaging
from oslo_config import cfg
from oslo_log import log as oslo_log

from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_client, get_rpc_server
from common.messaging.transport import get_transport
from common.schemas.requests import TargetHeartbeat, GatewayHeartbeat

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-scheduler"

# A target is considered dead after (heartbeat_interval * LIVENESS_MULTIPLIER) seconds.
LIVENESS_MULTIPLIER = 3


# ---------------------------------------------------------------------------
# In-memory target registry
# ---------------------------------------------------------------------------

@dataclass
class _TargetRecord:
    target_id: str
    hostname: str
    status: str
    last_seen: datetime
    enabled_drivers: list[str] = field(default_factory=list)
    labels: dict = field(default_factory=dict)


class _TargetRegistry:
    """
    Thread-safe in-memory registry of known targets and their liveness.

    The registry is authoritative for routing decisions.
    Persistence is delegated to the conductor via RPC.
    """

    def __init__(self) -> None:
        self._targets: dict[str, _TargetRecord] = {}
        self._lock = threading.RLock()

    def update(self, heartbeat: TargetHeartbeat) -> None:
        with self._lock:
            self._targets[heartbeat.target_id] = _TargetRecord(
                target_id=heartbeat.target_id,
                hostname=heartbeat.hostname,
                status=heartbeat.status,
                last_seen=datetime.now(timezone.utc),
                enabled_drivers=heartbeat.enabled_drivers,
                labels=heartbeat.labels,
            )

    def is_alive(self, target_id: str, heartbeat_interval_seconds: int) -> bool:
        """Return True if the target's last heartbeat is within the liveness window."""
        with self._lock:
            record = self._targets.get(target_id)
            if record is None:
                return False
            threshold = heartbeat_interval_seconds * LIVENESS_MULTIPLIER
            age = (datetime.now(timezone.utc) - record.last_seen).total_seconds()
            return age <= threshold

    def mark_stale(self, heartbeat_interval_seconds: int) -> list[str]:
        """
        Mark targets that have exceeded the liveness window as 'inactive'.
        Returns the list of target_ids that were marked stale.
        """
        stale = []
        with self._lock:
            threshold = heartbeat_interval_seconds * LIVENESS_MULTIPLIER
            now = datetime.now(timezone.utc)
            for target_id, record in self._targets.items():
                age = (now - record.last_seen).total_seconds()
                if age > threshold and record.status != "inactive":
                    record.status = "inactive"
                    stale.append(target_id)
        return stale

    def get_all(self) -> list[_TargetRecord]:
        with self._lock:
            return list(self._targets.values())

    def get(self, target_id: str) -> _TargetRecord | None:
        with self._lock:
            return self._targets.get(target_id)


# ---------------------------------------------------------------------------
# Stale-target reaper (background daemon thread)
# ---------------------------------------------------------------------------

class _StaleTargetReaper(threading.Thread):
    """
    Periodically scans the registry for targets that have stopped sending
    heartbeats and notifies the conductor to update their DB status.
    """

    def __init__(self, conf, registry: _TargetRegistry, get_conductor_client_fn) -> None:
        super().__init__(daemon=True, name="stale-target-reaper")
        self._conf = conf
        self._registry = registry
        self._get_conductor_client = get_conductor_client_fn
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        # Check every heartbeat_interval seconds
        # We need a default here since the reaper is started before CONF is fully wired
        heartbeat_interval = 30  # sensible default; overridden via oslo.config in target

        while not self._stop.wait(timeout=heartbeat_interval):
            stale = self._registry.mark_stale(heartbeat_interval)
            for target_id in stale:
                LOG.warning("Target %r has gone stale (no heartbeat)", target_id)
                try:
                    client = self._get_conductor_client()
                    client.cast(
                        {},
                        "update_target_status",
                        target_id=target_id,
                        hostname="",
                        status="inactive",
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                        enabled_drivers=[],
                        labels={},
                    )
                except Exception as exc:
                    LOG.error(
                        "Failed to notify conductor of stale target %r: %s", target_id, exc
                    )


# ---------------------------------------------------------------------------
# RPC Endpoint
# ---------------------------------------------------------------------------

class SchedulerRPCEndpoint:
    """
    oslo.messaging RPC endpoint for sentinel-scheduler.

    Methods
    -------
    target_heartbeat  — cast from sentinel-target (no reply needed)
    gateway_heartbeat — cast from sentinel-target in gateway mode (no reply needed)
    dispatch          — call from sentinel-conductor (returns routing result)
    list_targets      — call from conductor/CLI for observability
    """

    target = oslo_messaging.Target(version="1.0")

    def __init__(self, conf, registry: _TargetRegistry, transport) -> None:
        self._conf = conf
        self._registry = registry
        self._transport = transport
        self._conductor_client = None
        self._conductor_client_lock = threading.Lock()

    def _get_conductor_client(self):
        """Lazily initialise the conductor RPC client."""
        if self._conductor_client is not None:
            return self._conductor_client
        with self._conductor_client_lock:
            if self._conductor_client is None:
                self._conductor_client = get_rpc_client(
                    self._transport,
                    topic=self._conf.messaging.rpc_topic_conductor,
                )
        return self._conductor_client

    # ------------------------------------------------------------------
    # target_heartbeat — cast from targets (no return value required)
    # ------------------------------------------------------------------

    def target_heartbeat(self, ctxt: dict, heartbeat: dict) -> None:
        """
        Receive a heartbeat from a sentinel-target and update the registry.

        Also notifies the conductor to persist the target status to DB.
        This method is called via ``cast`` so it returns nothing.
        """
        try:
            hb = TargetHeartbeat(**heartbeat)
        except Exception as exc:
            LOG.error("Malformed heartbeat payload: %s — %s", heartbeat, exc)
            return

        self._registry.update(hb)
        LOG.debug("Heartbeat received: target_id=%r hostname=%r", hb.target_id, hb.hostname)

        # Notify conductor to persist target status (fire-and-forget)
        try:
            self._get_conductor_client().cast(
                ctxt,
                "update_target_status",
                target_id=hb.target_id,
                hostname=hb.hostname,
                status=hb.status,
                last_heartbeat=hb.timestamp.isoformat(),
                enabled_drivers=hb.enabled_drivers,
                labels=hb.labels,
                target_type=hb.target_type,
                gateway_id=hb.gateway_id,
            )
        except Exception as exc:
            # Non-fatal: in-memory state is updated; DB update will retry on next heartbeat
            LOG.warning(
                "Could not notify conductor of heartbeat for target %r: %s",
                hb.target_id, exc,
            )

    # ------------------------------------------------------------------
    # gateway_heartbeat — cast from gateway-mode targets (no return value)
    # ------------------------------------------------------------------

    def gateway_heartbeat(self, ctxt: dict, heartbeat: dict) -> None:
        """
        Receive a heartbeat from a sentinel-target running in gateway mode.

        Notifies the conductor to persist the gateway status to DB.
        This method is called via ``cast`` so it returns nothing.
        """
        try:
            hb = GatewayHeartbeat(**heartbeat)
        except Exception as exc:
            LOG.error("Malformed gateway heartbeat payload: %s — %s", heartbeat, exc)
            return

        LOG.debug("Gateway heartbeat received: gateway_id=%r hostname=%r", hb.gateway_id, hb.hostname)

        # Notify conductor to persist gateway status (fire-and-forget)
        try:
            self._get_conductor_client().cast(
                ctxt,
                "update_gateway_status",
                gateway_id=hb.gateway_id,
                hostname=hb.hostname,
                status=hb.status,
                last_heartbeat=hb.timestamp.isoformat(),
                managed_target_ids=hb.managed_target_ids,
                labels=hb.labels,
            )
        except Exception as exc:
            LOG.warning(
                "Could not notify conductor of gateway heartbeat for %r: %s",
                hb.gateway_id, exc,
            )

    # ------------------------------------------------------------------
    # dispatch — call from conductor (synchronous, returns routing result)
    # ------------------------------------------------------------------

    def dispatch(self, ctxt: dict, payload: dict, target_id: str) -> dict:
        """
        Route a signed execution payload to the target.

        Called by ``sentinel-conductor`` after RBAC check and RSA signing.

        Args:
            payload:   Fully signed ``ExecutionPayload`` dict.
            target_id: Target identifier.

        Returns:
            ``{"status": "queued"}`` on success.
            ``{"status": "target_unreachable", "reason": str}`` if the target
            is not alive according to the heartbeat registry.
        """
        # Liveness check (use target's configured heartbeat interval as threshold base)
        # We use a conservative 30s default; in production this comes from [target] config
        heartbeat_interval = 30

        if not self._registry.is_alive(target_id, heartbeat_interval):
            record = self._registry.get(target_id)
            if record is None:
                reason = f"Target {target_id!r} has never sent a heartbeat."
            else:
                age = (datetime.now(timezone.utc) - record.last_seen).total_seconds()
                reason = (
                    f"Target {target_id!r} last seen {age:.0f}s ago "
                    f"(threshold: {heartbeat_interval * LIVENESS_MULTIPLIER}s)."
                )
            LOG.warning("dispatch: target_unreachable target_id=%r — %s", target_id, reason)
            return {"status": "target_unreachable", "reason": reason}

        # Cast to the target's dedicated queue: sentinel.target.<target_id>
        try:
            target_client = get_rpc_client(
                self._transport,
                topic=self._conf.messaging.target_queue_prefix,
                server=target_id,
            )
            target_client.cast(ctxt, "execute_payload", payload=payload)
        except Exception as exc:
            LOG.error(
                "Failed to cast payload to target %r: %s", target_id, exc
            )
            return {"status": "dispatch_error", "reason": str(exc)}

        LOG.info(
            "Payload dispatched: message_id=%s → target=%r",
            payload.get("message_id", "unknown"),
            target_id,
        )
        return {"status": "queued"}

    # ------------------------------------------------------------------
    # list_targets — informational, called by CLI and admin API
    # ------------------------------------------------------------------

    def list_targets(self, ctxt: dict) -> list[dict]:
        """Return the current snapshot of all known targets and their liveness."""
        heartbeat_interval = 30
        records = self._registry.get_all()
        return [
            {
                "target_id": r.target_id,
                "hostname": r.hostname,
                "status": r.status,
                "last_seen": r.last_seen.isoformat(),
                "alive": self._registry.is_alive(r.target_id, heartbeat_interval),
                "enabled_drivers": r.enabled_drivers,
                "labels": r.labels,
            }
            for r in records
        ]


# ---------------------------------------------------------------------------
# oslo.config registration
# ---------------------------------------------------------------------------

def _register_opts() -> None:
    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _register_opts()
    oslo_log.register_options(CONF)

    conf_file = os.environ.get("SENTINEL_CONF")
    default_files = [conf_file] if conf_file and os.path.exists(conf_file) else []
    CONF(
        args=sys.argv[1:],
        project=SERVICE_NAME,
        default_config_files=default_files,
    )

    oslo_log.setup(CONF, SERVICE_NAME)
    LOG.info("Starting %s", SERVICE_NAME)

    transport = get_transport(CONF)
    registry = _TargetRegistry()
    endpoint = SchedulerRPCEndpoint(conf=CONF, registry=registry, transport=transport)

    # Start stale-target reaper
    reaper = _StaleTargetReaper(
        conf=CONF,
        registry=registry,
        get_conductor_client_fn=endpoint._get_conductor_client,
    )
    reaper.start()

    # Start RPC server
    server = get_rpc_server(
        transport,
        topic=CONF.messaging.rpc_topic_scheduler,
        endpoints=[endpoint],
        server=SERVICE_NAME,
        executor="threading",
    )

    LOG.info(
        "RPC server listening on topic=%r server=%r",
        CONF.messaging.rpc_topic_scheduler,
        SERVICE_NAME,
    )

    try:
        server.start()
        server.wait()
    except KeyboardInterrupt:
        LOG.info("Shutdown requested")
    finally:
        reaper.stop()
        server.stop()
        server.wait()
        LOG.info("%s stopped", SERVICE_NAME)


if __name__ == "__main__":
    main()
