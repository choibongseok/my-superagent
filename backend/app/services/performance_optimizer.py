"""Performance optimization service for AgentHQ.

This module provides advanced caching strategies and query optimization
utilities to improve application performance and reduce latency.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.models.task import Task
from app.models.template import Template

T = TypeVar("T")


class QueryOptimizer:
    """Utilities for optimizing database queries."""

    @staticmethod
    def enable_query_logging():
        """Enable SQL query logging for debugging performance issues."""

        @event.listens_for(Engine, "before_cursor_execute")
        def receive_before_cursor_execute(
            conn, cursor, statement, params, context, executemany
        ):
            conn.info.setdefault("query_start_time", []).append(time.time())

        @event.listens_for(Engine, "after_cursor_execute")
        def receive_after_cursor_execute(
            conn, cursor, statement, params, context, executemany
        ):
            total = time.time() - conn.info["query_start_time"].pop(-1)
            if total > 0.1:  # Log slow queries (>100ms)
                print(f"SLOW QUERY ({total:.3f}s): {statement}")

    @staticmethod
    async def get_user_with_cache(
        db: AsyncSession,
        user_id: str,
        ttl: int = 300,  # 5 minutes
    ) -> Optional[User]:
        """Get user by ID with Redis caching.

        Args:
            db: Database session
            user_id: User UUID
            ttl: Cache TTL in seconds

        Returns:
            User object or None
        """
        cache_key = f"user:{user_id}"

        # Try cache first
        cached = await cache.get(cache_key)
        if cached:
            return User(**cached)

        # Query database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            # Cache the result
            user_dict = {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
            }
            await cache.set(cache_key, user_dict, ttl)

        return user

    @staticmethod
    async def get_workspace_members_with_cache(
        db: AsyncSession,
        workspace_id: str,
        ttl: int = 600,  # 10 minutes
    ) -> list[WorkspaceMember]:
        """Get workspace members with eager loading and caching.

        Args:
            db: Database session
            workspace_id: Workspace UUID
            ttl: Cache TTL in seconds

        Returns:
            List of workspace members
        """
        cache_key = f"workspace_members:{workspace_id}"

        # Try cache first
        cached = await cache.get(cache_key)
        if cached:
            return [WorkspaceMember(**m) for m in cached]

        # Query with eager loading to avoid N+1 queries
        result = await db.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .options(selectinload(WorkspaceMember.user))
        )
        members = result.scalars().all()

        # Cache the result
        members_data = [
            {
                "id": str(m.id),
                "workspace_id": str(m.workspace_id),
                "user_id": str(m.user_id),
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m in members
        ]
        await cache.set(cache_key, members_data, ttl)

        return members

    @staticmethod
    async def get_user_tasks_optimized(
        db: AsyncSession,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """Get user tasks with optimized query (indexed and limited).

        Args:
            db: Database session
            user_id: User UUID
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip

        Returns:
            List of tasks
        """
        # Use indexed columns and limit results
        result = await db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def invalidate_user_cache(user_id: str) -> None:
        """Invalidate all cache entries for a user.

        Args:
            user_id: User UUID
        """
        await cache.delete_pattern(f"user:{user_id}*")

    @staticmethod
    async def invalidate_workspace_cache(workspace_id: str) -> None:
        """Invalidate all cache entries for a workspace.

        Args:
            workspace_id: Workspace UUID
        """
        await cache.delete_pattern(f"workspace*:{workspace_id}*")


class PromptOptimizer:
    """Utilities for optimizing LLM prompts to reduce token usage."""

    @staticmethod
    def compress_whitespace(text: str) -> str:
        """Remove extra whitespace from text.

        Args:
            text: Input text

        Returns:
            Compressed text
        """
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def truncate_context(
        context: str,
        max_chars: int = 4000,
        keep_start: bool = True,
    ) -> str:
        """Truncate context to fit within token limits.

        Args:
            context: Input context
            max_chars: Maximum characters (rough token approximation: 1 token ≈ 4 chars)
            keep_start: Keep the start (True) or end (False) of the context

        Returns:
            Truncated context
        """
        if len(context) <= max_chars:
            return context

        if keep_start:
            return context[:max_chars] + "\n...[truncated]"
        else:
            return "...[truncated]\n" + context[-max_chars:]

    @staticmethod
    def create_cache_key(prompt: str, model: str, **kwargs) -> str:
        """Create a cache key for LLM responses.

        Args:
            prompt: The prompt text
            model: Model name
            **kwargs: Additional parameters

        Returns:
            Cache key string
        """
        # Create a hash of the prompt + model + params
        content = f"{prompt}:{model}:{sorted(kwargs.items())}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()
        return f"llm_response:{model}:{hash_digest[:16]}"

    @staticmethod
    async def get_cached_llm_response(
        prompt: str,
        model: str,
        ttl: int = 3600,  # 1 hour
        **kwargs,
    ) -> Optional[str]:
        """Get cached LLM response if available.

        Args:
            prompt: The prompt text
            model: Model name
            ttl: Cache TTL in seconds
            **kwargs: Additional parameters

        Returns:
            Cached response or None
        """
        cache_key = PromptOptimizer.create_cache_key(prompt, model, **kwargs)
        return await cache.get(cache_key)

    @staticmethod
    async def cache_llm_response(
        prompt: str,
        model: str,
        response: str,
        ttl: int = 3600,
        **kwargs,
    ) -> None:
        """Cache LLM response.

        Args:
            prompt: The prompt text
            model: Model name
            response: The LLM response
            ttl: Cache TTL in seconds
            **kwargs: Additional parameters
        """
        cache_key = PromptOptimizer.create_cache_key(prompt, model, **kwargs)
        await cache.set(cache_key, response, ttl)


class AsyncOptimizer:
    """Utilities for optimizing async operations."""

    @staticmethod
    async def batch_execute(
        tasks: list[Callable[[], Any]],
        max_concurrent: int = 10,
    ) -> list[Any]:
        """Execute tasks with limited concurrency.

        Args:
            tasks: List of async callables
            max_concurrent: Maximum concurrent tasks

        Returns:
            List of results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_task(task):
            async with semaphore:
                return await task()

        return await asyncio.gather(*[limited_task(task) for task in tasks])

    @staticmethod
    def memoize_async(ttl: int = 300):
        """Decorator for memoizing async function results in memory.

        Args:
            ttl: Time to live in seconds

        Returns:
            Decorated function
        """
        _cache: dict[str, tuple[Any, float]] = {}

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                key = f"{func.__name__}:{args}:{sorted(kwargs.items())}"

                # Check cache
                if key in _cache:
                    result, expires_at = _cache[key]
                    if time.time() < expires_at:
                        return result
                    else:
                        del _cache[key]

                # Execute function
                result = await func(*args, **kwargs)

                # Store in cache
                _cache[key] = (result, time.time() + ttl)

                return result

            return wrapper

        return decorator


# Global optimizer instances
query_optimizer = QueryOptimizer()
prompt_optimizer = PromptOptimizer()
async_optimizer = AsyncOptimizer()
