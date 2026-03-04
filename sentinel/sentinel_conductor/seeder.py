"""
sentinel_conductor.seeder
===========================
Bootstrap helper: inserts default command sets when the database is
freshly initialised.

Controlled by the ``SENTINEL_SEED_DEFAULTS`` environment variable.
Set it to ``true`` (case-insensitive) to enable seeding on startup.

Usage::

    from sentinel_conductor.seeder import seed_default_command_sets
    from sentinel_conductor.db import get_session

    seeded = seed_default_command_sets(get_session)
    LOG.info("Seeded %d default command set(s)", seeded)
"""

import logging
from typing import Callable

from common.models import Command, CommandSet
from common.fixtures.default_command_sets import DEFAULT_COMMAND_SETS

LOG = logging.getLogger(__name__)


def seed_default_command_sets(session_factory: Callable) -> int:
    """
    Insert default command sets if they do not already exist.

    Each command set is identified by its unique ``name``.  If a
    command set with that name already exists it is skipped entirely
    (no update, no partial insert).  This makes the operation fully
    idempotent — safe to call on every startup.

    Args:
        session_factory: Context-manager callable that yields a
                         SQLAlchemy Session (e.g. ``get_session``).

    Returns:
        Number of command sets created (0 if all already existed).
    """
    created = 0
    for cs_data in DEFAULT_COMMAND_SETS:
        with session_factory() as session:
            from sqlalchemy import select
            existing = session.scalar(
                select(CommandSet).where(CommandSet.name == cs_data["name"])
            )
            if existing is not None:
                LOG.debug(
                    "Default command set %r already exists — skipping", cs_data["name"]
                )
                continue

            cs = CommandSet(
                name=cs_data["name"],
                driver=cs_data["driver"],
                description=cs_data.get("description"),
            )
            session.add(cs)
            session.flush()  # populate cs.id before creating Commands

            for cmd_data in cs_data.get("commands", []):
                cmd = Command(
                    command_set_id=cs.id,
                    name=cmd_data["name"],
                    binary=cmd_data["binary"],
                    args_regex=cmd_data.get("args_regex"),
                    require_2fa=cmd_data.get("require_2fa", False),
                    description=cmd_data.get("description"),
                    allowed_paths=cmd_data.get("allowed_paths"),
                )
                session.add(cmd)

            session.flush()
            created += 1
            LOG.info(
                "Seeded default command set %r with %d command(s)",
                cs_data["name"],
                len(cs_data.get("commands", [])),
            )

    return created
