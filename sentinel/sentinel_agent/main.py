"""
sentinel_agent.main
====================
Service entry point for sentinel-agent.

Startup sequence:
  1. Register oslo.config option groups.
  2. Parse CLI args / config file.
  3. Configure logging.
  4. Determine agent_id (from config or hostname).
  5. Load conductor's RSA public key (PayloadVerifier).
  6. Start heartbeat thread → periodic casts to sentinel.scheduler.
  7. Start oslo.messaging RPC server on topic ``sentinel.agent.<agent_id>``
     (blocking until SIGINT/SIGTERM).

Security note: the agent opens NO listening network sockets.
All communication is outbound to RabbitMQ only.
"""

import logging
import os
import socket
import sys
import threading
import time

from oslo_config import cfg
from oslo_log import log as oslo_log

from common.config.agent import agent_group, agent_opts
from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_client, get_rpc_server
from common.messaging.transport import get_transport
from common.schemas.requests import AgentHeartbeat
from sentinel_agent.crypto import PayloadVerifier
from sentinel_agent.rpc.consumer import AgentRPCEndpoint

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-agent"


def _register_opts() -> None:
    CONF.register_group(agent_group)
    CONF.register_opts(agent_opts, group=agent_group)

    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)


def _resolve_agent_id(conf) -> str:
    """Return agent_id from config or fall back to the system hostname."""
    configured = conf.agent.agent_id
    if configured:
        return configured
    hostname = socket.gethostname()
    LOG.info("No agent_id configured — using hostname: %r", hostname)
    return hostname


class _HeartbeatThread(threading.Thread):
    """
    Daemon thread that periodically casts AgentHeartbeat messages to
    sentinel-scheduler's RPC topic.

    Uses oslo.messaging ``cast`` (fire-and-forget) — scheduler downtime
    does NOT block agent operation.
    """

    def __init__(self, conf, agent_id: str, transport) -> None:
        super().__init__(daemon=True, name="agent-heartbeat")
        self._conf = conf
        self._agent_id = agent_id
        self._transport = transport
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        interval = self._conf.agent.heartbeat_interval_seconds
        client = get_rpc_client(
            self._transport,
            topic=self._conf.messaging.rpc_topic_scheduler,
        )

        LOG.info(
            "Heartbeat thread started: agent_id=%r interval=%ds",
            self._agent_id, interval,
        )

        while not self._stop_event.is_set():
            heartbeat = AgentHeartbeat(
                agent_id=self._agent_id,
                hostname=socket.gethostname(),
                status="active",
                enabled_drivers=list(self._conf.agent.enabled_drivers),
            )
            try:
                client.cast({}, "agent_heartbeat", heartbeat=heartbeat.model_dump(mode="json"))
                LOG.debug("Heartbeat sent: agent_id=%r", self._agent_id)
            except Exception as exc:
                # Heartbeat failure is non-fatal — log and continue
                LOG.warning("Heartbeat failed: %s", exc)

            self._stop_event.wait(timeout=interval)


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

    agent_id = _resolve_agent_id(CONF)
    LOG.info("Starting %s agent_id=%r", SERVICE_NAME, agent_id)

    # Load conductor's public key for payload verification
    try:
        verifier = PayloadVerifier.from_config(CONF)
        LOG.info("Conductor public key loaded successfully")
    except FileNotFoundError:
        LOG.critical(
            "Conductor public key not found at %s. "
            "Ensure the keygen container has run.",
            CONF.agent.conductor_public_key_path,
        )
        sys.exit(1)

    transport = get_transport(CONF)

    # Conductor RPC client — used only for fire-and-forget result reporting
    conductor_client = get_rpc_client(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
    )

    # Start heartbeat daemon
    heartbeat = _HeartbeatThread(CONF, agent_id, transport)
    heartbeat.start()

    # Build RPC endpoint
    endpoint = AgentRPCEndpoint(
        conf=CONF,
        verifier=verifier,
        conductor_client=conductor_client,
    )

    # Start RPC server on the agent's dedicated queue
    # Topic: sentinel.agent  Server: <agent_id>
    # → queue name: sentinel.agent.<agent_id>
    server = get_rpc_server(
        transport,
        topic=CONF.messaging.agent_queue_prefix,
        endpoints=[endpoint],
        server=agent_id,
        executor="threading",
    )

    LOG.info(
        "RPC server listening on topic=%r server=%r",
        CONF.messaging.agent_queue_prefix,
        agent_id,
    )

    try:
        server.start()
        server.wait()
    except KeyboardInterrupt:
        LOG.info("Shutdown requested")
    finally:
        heartbeat.stop()
        server.stop()
        server.wait()
        LOG.info("%s stopped", SERVICE_NAME)


if __name__ == "__main__":
    main()
