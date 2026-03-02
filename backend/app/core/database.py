"""Database configuration and session management."""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Create async engine with appropriate configuration based on the database type
engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,  # Verify connections before using
}

# Only add pool configuration for databases that support it (not SQLite)
if not settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "pool_recycle": 3600,  # Recycle connections after 1 hour
        "pool_timeout": 30,  # Timeout for getting connection from pool
    })

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class get_db_context:
    """
    Context manager for getting database session outside of FastAPI dependency injection.
    
    Usage:
        async with get_db_context() as db:
            # Use db session
    """
    
    def __init__(self):
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> AsyncSession:
        """Enter context and create session."""
        self.session = AsyncSessionLocal()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context and close session."""
        if self.session:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
            await self.session.close()
