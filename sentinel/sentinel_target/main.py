"""
sentinel_target.main
====================
Service entry point for sentinel-target.

Startup sequence:
  1. Register oslo.config option groups.
  2. Parse CLI args / config file.
  3. Configure logging.
  4. Determine target_id (from config or hostname).
  5. Load conductor's RSA public key (PayloadVerifier).
  6. Start heartbeat thread → periodic casts to sentinel.scheduler.
  7. Start oslo.messaging RPC server on topic ``sentinel.target.<target_id>``
     (blocking until SIGINT/SIGTERM).

Operating modes
---------------
  direct  — executes commands locally via stevedore drivers.
  gateway — proxies execution to managed remote targets; also registers
            managed targets on their behalf via heartbeats.

Security note: sentinel-target opens NO listening network sockets.
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

from common.config.target import gateway_group, gateway_opts, target_group, target_opts
from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_client, get_rpc_server
from common.messaging.transport import get_transport
from common.schemas.requests import TargetHeartbeat
from sentinel_target.crypto import PayloadVerifier
from sentinel_target.rpc.consumer import TargetRPCEndpoint

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-target"


def _register_opts() -> None:
    CONF.register_group(target_group)
    CONF.register_opts(target_opts, group=target_group)

    CONF.register_group(gateway_group)
    CONF.register_opts(gateway_opts, group=gateway_group)

    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)


def _resolve_target_id(conf) -> str:
    """Return target_id from config or fall back to the system hostname."""
    configured = conf.target.target_id
    if configured:
        return configured
    hostname = socket.gethostname()
    LOG.info("No target_id configured — using hostname: %r", hostname)
    return hostname


class _HeartbeatThread(threading.Thread):
    """
    Daemon thread that periodically casts TargetHeartbeat messages to
    sentinel-scheduler's RPC topic.

    Uses oslo.messaging ``cast`` (fire-and-forget) — scheduler downtime
    does NOT block target operation.
    """

    def __init__(self, conf, target_id: str, transport) -> None:
        super().__init__(daemon=True, name="target-heartbeat")
        self._conf = conf
        self._target_id = target_id
        self._transport = transport
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        interval = self._conf.target.heartbeat_interval_seconds
        client = get_rpc_client(
            self._transport,
            topic=self._conf.messaging.rpc_topic_scheduler,
        )

        mode = self._conf.target.mode
        LOG.info(
            "Heartbeat thread started: target_id=%r mode=%r interval=%ds",
            self._target_id, mode, interval,
        )

        while not self._stop_event.is_set():
            heartbeat = TargetHeartbeat(
                target_id=self._target_id,
                hostname=socket.gethostname(),
                target_type=mode,
                status="active",
                enabled_drivers=list(self._conf.target.enabled_drivers),
            )
            try:
                client.cast({}, "target_heartbeat", heartbeat=heartbeat.model_dump(mode="json"))
                LOG.debug("Heartbeat sent: target_id=%r", self._target_id)
            except Exception as exc:
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

    target_id = _resolve_target_id(CONF)
    mode = CONF.target.mode
    LOG.info("Starting %s target_id=%r mode=%r", SERVICE_NAME, target_id, mode)

    # Load conductor's public key for payload verification
    try:
        verifier = PayloadVerifier.from_config(CONF)
        LOG.info("Conductor public key loaded successfully")
    except FileNotFoundError:
        LOG.critical(
            "Conductor public key not found at %s. "
            "Ensure the keygen container has run.",
            CONF.target.conductor_public_key_path,
        )
        sys.exit(1)

    transport = get_transport(CONF)

    # Conductor RPC client — used only for fire-and-forget result reporting
    conductor_client = get_rpc_client(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
    )

    # Start heartbeat daemon
    heartbeat = _HeartbeatThread(CONF, target_id, transport)
    heartbeat.start()

    # Build RPC endpoint
    endpoint = TargetRPCEndpoint(
        conf=CONF,
        verifier=verifier,
        conductor_client=conductor_client,
    )

    # Start RPC server on the target's dedicated queue
    # Topic: sentinel.target  Server: <target_id>
    # → queue name: sentinel.target.<target_id>
    server = get_rpc_server(
        transport,
        topic=CONF.messaging.target_queue_prefix,
        endpoints=[endpoint],
        server=target_id,
        executor="threading",
    )

    LOG.info(
        "RPC server listening on topic=%r server=%r mode=%r",
        CONF.messaging.target_queue_prefix,
        target_id,
        mode,
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
