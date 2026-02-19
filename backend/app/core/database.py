"""Database configuration and session management.

Engine and session factory are created lazily on first access to allow
test environments to override DATABASE_URL before any DB connection is made.
"""

from __future__ import annotations

import threading
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── Lazy engine / session factory ────────────────────────────────────────────
# We do NOT create the engine at module import time.
# This allows tests (and other tooling) to set DATABASE_URL before the first
# real DB call is made, without triggering a connection attempt on import.

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_lock = threading.Lock()


def _get_engine() -> AsyncEngine:
    """Return (or create) the singleton async engine."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = create_async_engine(
                    settings.DATABASE_URL,
                    echo=settings.DEBUG,
                    pool_size=settings.DATABASE_POOL_SIZE,
                    max_overflow=settings.DATABASE_MAX_OVERFLOW,
                    pool_pre_ping=True,   # Verify connections before using
                    pool_recycle=3600,    # Recycle after 1 hour
                    pool_timeout=30,      # Timeout for pool checkout
                )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (or create) the singleton session factory."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = async_sessionmaker(
                    _get_engine(),
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autocommit=False,
                    autoflush=False,
                )
    return _session_factory


def reset_engine(new_url: Optional[str] = None) -> None:
    """
    Tear down the current engine/factory and (optionally) set a new URL.

    Intended for test setup:

    .. code-block:: python

        # conftest.py
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
        reset_engine()          # ensure next access rebuilds with new URL

    Args:
        new_url: If given, overwrite ``settings.DATABASE_URL`` before reset.
    """
    global _engine, _session_factory
    with _lock:
        if new_url is not None:
            settings.DATABASE_URL = new_url  # type: ignore[assignment]
        _engine = None
        _session_factory = None


# ── Compatibility shim ────────────────────────────────────────────────────────
# Code that does ``from app.core.database import engine`` still works, but it
# now gets a proxy that resolves lazily.  For the vast majority of production
# paths (where the engine is needed *after* import) this is transparent.


class _EngineProxy:
    """Thin proxy that forwards attribute access to the real engine."""

    def __getattr__(self, name: str):  # type: ignore[override]
        return getattr(_get_engine(), name)

    def __repr__(self) -> str:
        return repr(_get_engine())


# Public names kept for backward-compat
engine: AsyncEngine = _EngineProxy()  # type: ignore[assignment]
AsyncSessionLocal = property(lambda self: _get_session_factory())  # type: ignore


# ── ORM base ─────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    type_annotation_map = {
        UUID: Uuid(as_uuid=True),
    }


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session dependency for FastAPI routes.

    Commits on success, rolls back on exception, always closes.

    Yields:
        AsyncSession: Active database session.
    """
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
