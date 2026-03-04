"""
sentinel_conductor.db
======================
SQLAlchemy engine and session factory for sentinel-conductor.

This is the ONLY module in the entire system that creates DB connections.
No other component (agent, scheduler, APIs) accesses the DB directly —
they go through the conductor via oslo.messaging RPC.

Usage::

    from sentinel_conductor.db import init_db, get_session

    # At startup:
    init_db(CONF)

    # In a handler:
    with get_session() as session:
        agent = session.scalar(select(Agent).where(...))
        ...
        # session.commit() is called automatically on clean exit
"""

import threading
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None
_lock = threading.Lock()


def init_db(conf) -> None:
    """
    Initialise the SQLAlchemy engine from oslo.config.

    Thread-safe — safe to call multiple times (no-op if already initialised).

    Args:
        conf: oslo.config CONF object with [database] group registered.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return

    with _lock:
        if _engine is not None:
            return

        _engine = create_engine(
            conf.database.connection,
            pool_size=conf.database.pool_size,
            max_overflow=conf.database.max_overflow,
            echo=conf.database.echo,
            # Recycle connections after 30 min to avoid stale connections
            pool_recycle=1800,
            # Test connectivity before handing connection to caller
            pool_pre_ping=True,
        )
        _SessionLocal = sessionmaker(
            bind=_engine,
            expire_on_commit=False,  # Avoid lazy-load errors after commit
            autoflush=False,
        )


def get_engine():
    """Return the initialised SQLAlchemy engine (for Alembic and tests)."""
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db(conf) first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a transactional database session as a context manager.

    Commits on clean exit, rolls back on exception, always closes.

    Example::

        with get_session() as session:
            session.add(some_model)
            # commit happens automatically

    Raises:
        RuntimeError: if ``init_db()`` has not been called.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db(conf) first.")

    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_db() -> None:
    """
    Reset the cached engine and session factory.
    Intended for use in tests only.
    """
    global _engine, _SessionLocal
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _SessionLocal = None
