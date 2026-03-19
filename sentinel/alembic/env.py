"""
Alembic environment — integrates with oslo.config.

The database URL is sourced from oslo.config ``[database] connection``
so that migrations always use the same credentials as the running service.

Running migrations:

    # From within the sentinel/ package directory (or via Docker):
    SENTINEL_CONF=/etc/sentinel/sentinel.conf alembic upgrade head

    # Or via docker-compose:
    docker compose run --rm migrate
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from oslo_config import cfg
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Make sure the sentinel package is importable from this script
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Import all models so Alembic's autogenerate can detect them
# ---------------------------------------------------------------------------
from common.models import Base  # noqa: E402  (import after sys.path manipulation)
from common.models import (  # noqa: F401 — side-effect: registers all table metadata
    Gateway,
    Target,
    HostGroup,
    TargetGroupMembership,
    CommandSet,
    Command,
    RoleBinding,
    AuditLog,
    User,
    TwoFAChallenge,
)

# ---------------------------------------------------------------------------
# oslo.config bootstrap
# ---------------------------------------------------------------------------
CONF = cfg.CONF

# Register [database] options so oslo.config can parse them
from common.config.database import database_group, database_opts  # noqa: E402

CONF.register_group(database_group)
CONF.register_opts(database_opts, group=database_group)

# Parse config file from the environment variable (or fall back to defaults)
_conf_file = os.environ.get("SENTINEL_CONF")
if _conf_file and os.path.exists(_conf_file):
    CONF(args=[], default_config_files=[_conf_file])
else:
    CONF(args=[])

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------
alembic_cfg = context.config

# Inject the DB URL from oslo.config into Alembic's config
alembic_cfg.set_main_option("sqlalchemy.url", CONF.database.connection)

# Attach Python logging configuration from alembic.ini
if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    In offline mode Alembic emits SQL to stdout instead of executing it,
    which is useful for generating migration scripts for review.
    """
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (connects to the live database).
    """
    connectable = engine_from_config(
        alembic_cfg.get_section(alembic_cfg.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Use NullPool in migration scripts (single connection)
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
