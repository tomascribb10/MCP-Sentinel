"""
sentinel_scheduler.main
========================
Service entry point and RPC endpoint for sentinel-scheduler.

Responsibilities
----------------
1. **Heartbeat reception**: receives ``agent_heartbeat`` casts from all
   sentinel-agent daemons and maintains an in-memory liveness registry.

2. **DB persistence**: after each heartbeat, calls
   ``conductor.update_agent_status()`` via RPC so the conductor can
   persist agent state to the central DB (conductor is the only component
   with DB access).

3. **Execution routing**: receives ``dispatch`` calls from the conductor
   (after RBAC + signing), performs an agent liveness check, and casts
   the signed payload to the agent's dedicated queue
   ``sentinel.agent.<agent_id>``.

Message flow
------------
  Agent  ──cast──►  Scheduler.agent_heartbeat()
                         └─ registry.update()
                         └─ conductor.update_agent_status()  [cast, non-blocking]

  Conductor  ──call──►  Scheduler.dispatch(payload, agent_id)
                             └─ registry.is_alive(agent_id) ?
                             │      YES → cast to sentinel.agent.<agent_id>
                             │             return {"status": "queued"}
                             └─────── NO  → return {"status": "agent_unreachable"}
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
from common.schemas.requests import AgentHeartbeat

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-scheduler"

# An agent is considered dead after (heartbeat_interval * LIVENESS_MULTIPLIER) seconds.
LIVENESS_MULTIPLIER = 3


# ---------------------------------------------------------------------------
# In-memory agent registry
# ---------------------------------------------------------------------------

@dataclass
class _AgentRecord:
    agent_id: str
    hostname: str
    status: str
    last_seen: datetime
    enabled_drivers: list[str] = field(default_factory=list)
    labels: dict = field(default_factory=dict)


class _AgentRegistry:
    """
    Thread-safe in-memory registry of known agents and their liveness.

    The registry is authoritative for routing decisions.
    Persistence is delegated to the conductor via RPC.
    """

    def __init__(self) -> None:
        self._agents: dict[str, _AgentRecord] = {}
        self._lock = threading.RLock()

    def update(self, heartbeat: AgentHeartbeat) -> None:
        with self._lock:
            self._agents[heartbeat.agent_id] = _AgentRecord(
                agent_id=heartbeat.agent_id,
                hostname=heartbeat.hostname,
                status=heartbeat.status,
                last_seen=datetime.now(timezone.utc),
                enabled_drivers=heartbeat.enabled_drivers,
                labels=heartbeat.labels,
            )

    def is_alive(self, agent_id: str, heartbeat_interval_seconds: int) -> bool:
        """Return True if the agent's last heartbeat is within the liveness window."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return False
            threshold = heartbeat_interval_seconds * LIVENESS_MULTIPLIER
            age = (datetime.now(timezone.utc) - record.last_seen).total_seconds()
            return age <= threshold

    def mark_stale(self, heartbeat_interval_seconds: int) -> list[str]:
        """
        Mark agents that have exceeded the liveness window as 'inactive'.
        Returns the list of agent_ids that were marked stale.
        """
        stale = []
        with self._lock:
            threshold = heartbeat_interval_seconds * LIVENESS_MULTIPLIER
            now = datetime.now(timezone.utc)
            for agent_id, record in self._agents.items():
                age = (now - record.last_seen).total_seconds()
                if age > threshold and record.status != "inactive":
                    record.status = "inactive"
                    stale.append(agent_id)
        return stale

    def get_all(self) -> list[_AgentRecord]:
        with self._lock:
            return list(self._agents.values())

    def get(self, agent_id: str) -> _AgentRecord | None:
        with self._lock:
            return self._agents.get(agent_id)


# ---------------------------------------------------------------------------
# Stale-agent reaper (background daemon thread)
# ---------------------------------------------------------------------------

class _StaleAgentReaper(threading.Thread):
    """
    Periodically scans the registry for agents that have stopped sending
    heartbeats and notifies the conductor to update their DB status.
    """

    def __init__(self, conf, registry: _AgentRegistry, get_conductor_client_fn) -> None:
        super().__init__(daemon=True, name="stale-agent-reaper")
        self._conf = conf
        self._registry = registry
        self._get_conductor_client = get_conductor_client_fn
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        # Check every heartbeat_interval seconds
        # We need a default here since the reaper is started before CONF is fully wired
        interval = getattr(self._conf.messaging, "rpc_timeout", 60)
        heartbeat_interval = 30  # sensible default; overridden via oslo.config in agent

        while not self._stop.wait(timeout=heartbeat_interval):
            stale = self._registry.mark_stale(heartbeat_interval)
            for agent_id in stale:
                LOG.warning("Agent %r has gone stale (no heartbeat)", agent_id)
                try:
                    client = self._get_conductor_client()
                    client.cast(
                        {},
                        "update_agent_status",
                        agent_id=agent_id,
                        hostname="",
                        status="inactive",
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                        enabled_drivers=[],
                        labels={},
                    )
                except Exception as exc:
                    LOG.error(
                        "Failed to notify conductor of stale agent %r: %s", agent_id, exc
                    )


# ---------------------------------------------------------------------------
# RPC Endpoint
# ---------------------------------------------------------------------------

class SchedulerRPCEndpoint:
    """
    oslo.messaging RPC endpoint for sentinel-scheduler.

    Methods
    -------
    agent_heartbeat   — cast from sentinel-agent (no reply needed)
    dispatch          — call from sentinel-conductor (returns routing result)
    list_agents       — call from conductor/CLI for observability
    """

    target = oslo_messaging.Target(version="1.0")

    def __init__(self, conf, registry: _AgentRegistry, transport) -> None:
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
    # agent_heartbeat — cast from agents (no return value required)
    # ------------------------------------------------------------------

    def agent_heartbeat(self, ctxt: dict, heartbeat: dict) -> None:
        """
        Receive a heartbeat from a sentinel-agent and update the registry.

        Also notifies the conductor to persist the agent status to DB.
        This method is called via ``cast`` so it returns nothing.
        """
        try:
            hb = AgentHeartbeat(**heartbeat)
        except Exception as exc:
            LOG.error("Malformed heartbeat payload: %s — %s", heartbeat, exc)
            return

        self._registry.update(hb)
        LOG.debug("Heartbeat received: agent_id=%r hostname=%r", hb.agent_id, hb.hostname)

        # Notify conductor to persist agent status (fire-and-forget)
        try:
            self._get_conductor_client().cast(
                ctxt,
                "update_agent_status",
                agent_id=hb.agent_id,
                hostname=hb.hostname,
                status=hb.status,
                last_heartbeat=hb.timestamp.isoformat(),
                enabled_drivers=hb.enabled_drivers,
                labels=hb.labels,
            )
        except Exception as exc:
            # Non-fatal: in-memory state is updated; DB update will retry on next heartbeat
            LOG.warning(
                "Could not notify conductor of heartbeat for agent %r: %s",
                hb.agent_id, exc,
            )

    # ------------------------------------------------------------------
    # dispatch — call from conductor (synchronous, returns routing result)
    # ------------------------------------------------------------------

    def dispatch(self, ctxt: dict, payload: dict, agent_id: str) -> dict:
        """
        Route a signed execution payload to the target agent.

        Called by ``sentinel-conductor`` after RBAC check and RSA signing.

        Args:
            payload:   Fully signed ``ExecutionPayload`` dict.
            agent_id:  Target agent identifier.

        Returns:
            ``{"status": "queued"}`` on success.
            ``{"status": "agent_unreachable", "reason": str}`` if the agent
            is not alive according to the heartbeat registry.
        """
        # Liveness check (use agent's configured heartbeat interval as threshold base)
        # We use a conservative 30s default; in production this comes from [agent] config
        heartbeat_interval = 30

        if not self._registry.is_alive(agent_id, heartbeat_interval):
            record = self._registry.get(agent_id)
            if record is None:
                reason = f"Agent {agent_id!r} has never sent a heartbeat."
            else:
                age = (datetime.now(timezone.utc) - record.last_seen).total_seconds()
                reason = (
                    f"Agent {agent_id!r} last seen {age:.0f}s ago "
                    f"(threshold: {heartbeat_interval * LIVENESS_MULTIPLIER}s)."
                )
            LOG.warning("dispatch: agent_unreachable agent_id=%r — %s", agent_id, reason)
            return {"status": "agent_unreachable", "reason": reason}

        # Cast to the agent's dedicated queue: sentinel.agent.<agent_id>
        try:
            agent_client = get_rpc_client(
                self._transport,
                topic=self._conf.messaging.agent_queue_prefix,
                server=agent_id,
            )
            agent_client.cast(ctxt, "execute_payload", payload=payload)
        except Exception as exc:
            LOG.error(
                "Failed to cast payload to agent %r: %s", agent_id, exc
            )
            return {"status": "dispatch_error", "reason": str(exc)}

        LOG.info(
            "Payload dispatched: message_id=%s → agent=%r",
            payload.get("message_id", "unknown"),
            agent_id,
        )
        return {"status": "queued"}

    # ------------------------------------------------------------------
    # list_agents — informational, called by CLI and admin API
    # ------------------------------------------------------------------

    def list_agents(self, ctxt: dict) -> list[dict]:
        """Return the current snapshot of all known agents and their liveness."""
        heartbeat_interval = 30
        records = self._registry.get_all()
        return [
            {
                "agent_id": r.agent_id,
                "hostname": r.hostname,
                "status": r.status,
                "last_seen": r.last_seen.isoformat(),
                "alive": self._registry.is_alive(r.agent_id, heartbeat_interval),
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
    registry = _AgentRegistry()
    endpoint = SchedulerRPCEndpoint(conf=CONF, registry=registry, transport=transport)

    # Start stale-agent reaper
    reaper = _StaleAgentReaper(
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
