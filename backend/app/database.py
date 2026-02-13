"""Compatibility module for legacy database imports.

Historically parts of the codebase (and E2E tests) imported database
symbols from ``app.database``. The project was later refactored to
``app.core.database``. This shim preserves backward compatibility while
keeping the single source of truth in ``app.core.database``.
"""

from app.core.database import AsyncSessionLocal, Base, engine, get_db

__all__ = ["engine", "AsyncSessionLocal", "Base", "get_db"]
