"""
sentinel_conductor.main
========================
Service entry point for sentinel-conductor.

Startup sequence:
  1. Register oslo.config option groups.
  2. Parse CLI args / config file.
  3. Configure logging.
  4. Initialise database (SQLAlchemy engine + Alembic check).
  5. Load RSA private key.
  6. Load 2FA provider plugin via stevedore.
  7. Start oslo.messaging RPC server (blocking).
"""

import logging
import os
import sys

from oslo_config import cfg
from oslo_log import log as oslo_log
from stevedore import driver as stevedore_driver

from common.config.auth import auth_group, auth_opts, telegram_group, telegram_opts
from common.config.conductor import conductor_group, conductor_opts
from common.config.database import database_group, database_opts
from common.config.messaging import messaging_group, messaging_opts
from common.messaging.rpc import get_rpc_server
from common.messaging.transport import get_transport
from sentinel_conductor.crypto import load_private_key
from sentinel_conductor.db import init_db, get_session
from sentinel_conductor.rpc.server import ConductorRPCEndpoint
from sentinel_conductor.seeder import seed_default_command_sets

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

SERVICE_NAME = "sentinel-conductor"


def _register_opts() -> None:
    """Register all oslo.config option groups used by this service."""
    CONF.register_group(database_group)
    CONF.register_opts(database_opts, group=database_group)

    CONF.register_group(messaging_group)
    CONF.register_opts(messaging_opts, group=messaging_group)

    CONF.register_group(conductor_group)
    CONF.register_opts(conductor_opts, group=conductor_group)

    CONF.register_group(auth_group)
    CONF.register_opts(auth_opts, group=auth_group)

    CONF.register_group(telegram_group)
    CONF.register_opts(telegram_opts, group=telegram_group)


def _bootstrap_admin_user(session_factory) -> None:
    """
    Create the initial superuser if the users table is empty.

    Reads SENTINEL_INITIAL_ADMIN_USER (default: 'admin') and
    SENTINEL_INITIAL_ADMIN_PASSWORD from the environment.  If the
    password env var is not set, the bootstrap step is skipped.
    """
    import bcrypt
    from sqlalchemy import select, func
    from common.models import User

    password = os.environ.get("SENTINEL_INITIAL_ADMIN_PASSWORD")
    if not password:
        return

    username = os.environ.get("SENTINEL_INITIAL_ADMIN_USER", "admin")
    email = os.environ.get("SENTINEL_INITIAL_ADMIN_EMAIL", f"{username}@sentinel.local")

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(User))
        if count and count > 0:
            LOG.debug("Users table is non-empty — skipping bootstrap")
            return

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        session.add(User(
            username=username,
            email=email,
            hashed_password=hashed,
            is_active=True,
            is_superuser=True,
        ))
        LOG.info("Bootstrap: created initial superuser %r", username)


def _load_auth_provider(conf):
    """Load the configured 2FA provider plugin via stevedore."""
    provider_name = conf.auth.provider
    LOG.info("Loading 2FA provider plugin: %r", provider_name)

    kwargs = {}
    if provider_name == "telegram":
        kwargs = {
            "bot_token": conf.telegram.bot_token,
            "approver_chat_id": conf.telegram.approver_chat_id,
            "polling_interval_seconds": conf.telegram.polling_interval_seconds,
        }
    elif provider_name == "stub":
        kwargs = {"auto_approve": True, "auto_approve_delay_seconds": 1.0}

    try:
        mgr = stevedore_driver.DriverManager(
            namespace="sentinel.auth.providers",
            name=provider_name,
            invoke_on_load=True,
            invoke_kwds=kwargs,
        )
        return mgr.driver
    except Exception as exc:
        LOG.critical("Failed to load 2FA provider %r: %s", provider_name, exc)
        sys.exit(1)


def main() -> None:
    _register_opts()

    oslo_log.register_options(CONF)

    # Parse config file from env variable or CLI args
    conf_file = os.environ.get("SENTINEL_CONF")
    default_files = [conf_file] if conf_file and os.path.exists(conf_file) else []
    CONF(
        args=sys.argv[1:],
        project=SERVICE_NAME,
        default_config_files=default_files,
    )

    oslo_log.setup(CONF, SERVICE_NAME)
    LOG.info("Starting %s", SERVICE_NAME)

    # Initialise database
    init_db(CONF)
    LOG.info("Database connection initialised")

    # Bootstrap initial admin user (no-op if users already exist)
    _bootstrap_admin_user(get_session)

    # Seed default command sets (opt-in via SENTINEL_SEED_DEFAULTS=true)
    if os.environ.get("SENTINEL_SEED_DEFAULTS", "").lower() == "true":
        seeded = seed_default_command_sets(get_session)
        if seeded:
            LOG.info("Seeded %d default command set(s)", seeded)
        else:
            LOG.debug("Default command sets already present — nothing to seed")

    # Load RSA private key
    try:
        private_key = load_private_key(CONF.conductor.private_key_path)
        LOG.info("RSA private key loaded from %s", CONF.conductor.private_key_path)
    except FileNotFoundError:
        LOG.critical(
            "RSA private key not found at %s. "
            "Run the keygen container first.",
            CONF.conductor.private_key_path,
        )
        sys.exit(1)

    # Load 2FA provider
    auth_provider = _load_auth_provider(CONF)
    LOG.info("2FA provider loaded: %s", CONF.auth.provider)

    # Build RPC endpoint
    endpoint = ConductorRPCEndpoint(
        conf=CONF,
        session_factory=get_session,
        private_key=private_key,
        auth_provider=auth_provider,
    )

    # Start oslo.messaging RPC server
    transport = get_transport(CONF)
    server = get_rpc_server(
        transport,
        topic=CONF.messaging.rpc_topic_conductor,
        endpoints=[endpoint],
        server=SERVICE_NAME,
        executor="threading",
    )

    LOG.info(
        "RPC server listening on topic=%r server=%r",
        CONF.messaging.rpc_topic_conductor,
        SERVICE_NAME,
    )

    try:
        server.start()
        server.wait()
    except KeyboardInterrupt:
        LOG.info("Shutdown requested")
    finally:
        server.stop()
        server.wait()
        LOG.info("%s stopped", SERVICE_NAME)


if __name__ == "__main__":
    main()
