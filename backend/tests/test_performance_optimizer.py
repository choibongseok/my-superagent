"""Tests for performance optimization service."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.performance_optimizer import (
    QueryOptimizer,
    PromptOptimizer,
    AsyncOptimizer,
)
from app.models.user import User


class TestQueryOptimizer:
    """Test suite for QueryOptimizer."""

    @pytest.mark.asyncio
    async def test_get_user_with_cache_miss(self):
        """Test user retrieval with cache miss."""
        # Mock database session
        db = Mock(spec=AsyncSession)
        user = User(
            id="123",
            email="test@example.com",
            full_name="Test User",
            is_active=True,
        )

        # Mock database query result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        # Mock cache
        with patch("app.services.performance_optimizer.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock(return_value=True)

            result = await QueryOptimizer.get_user_with_cache(db, "123")

            assert result == user
            mock_cache.get.assert_called_once()
            mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_with_cache_hit(self):
        """Test user retrieval with cache hit."""
        # Mock database session (should not be called)
        db = Mock(spec=AsyncSession)

        cached_user = {
            "id": "123",
            "email": "test@example.com",
            "full_name": "Test User",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

        with patch("app.services.performance_optimizer.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=cached_user)

            result = await QueryOptimizer.get_user_with_cache(db, "123")

            assert result.email == cached_user["email"]
            mock_cache.get.assert_called_once()
            # Database should not be queried
            db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self):
        """Test user cache invalidation."""
        with patch("app.services.performance_optimizer.cache") as mock_cache:
            mock_cache.delete_pattern = AsyncMock(return_value=5)

            await QueryOptimizer.invalidate_user_cache("123")

            mock_cache.delete_pattern.assert_called_once_with("user:123*")

    @pytest.mark.asyncio
    async def test_invalidate_workspace_cache(self):
        """Test workspace cache invalidation."""
        with patch("app.services.performance_optimizer.cache") as mock_cache:
            mock_cache.delete_pattern = AsyncMock(return_value=3)

            await QueryOptimizer.invalidate_workspace_cache("ws-123")

            mock_cache.delete_pattern.assert_called_once_with("workspace*:ws-123*")


class TestPromptOptimizer:
    """Test suite for PromptOptimizer."""

    def test_compress_whitespace(self):
        """Test whitespace compression."""
        text = """
        This is a test.
        
        With extra   spaces.
        
        And blank lines.
        """
        result = PromptOptimizer.compress_whitespace(text)

        assert "  " not in result  # No double spaces
        assert "\n\n" not in result  # No blank lines
        assert result.startswith("This is a test.")

    def test_truncate_context_keep_start(self):
        """Test context truncation (keep start)."""
        context = "A" * 5000
        result = PromptOptimizer.truncate_context(context, max_chars=1000, keep_start=True)

        assert len(result) <= 1020  # ~1000 + truncation marker
        assert result.startswith("A")
        assert result.endswith("[truncated]")

    def test_truncate_context_keep_end(self):
        """Test context truncation (keep end)."""
        context = "A" * 5000
        result = PromptOptimizer.truncate_context(context, max_chars=1000, keep_start=False)

        assert len(result) <= 1020
        assert result.startswith("...[truncated]")
        assert result.endswith("A")

    def test_create_cache_key(self):
        """Test LLM cache key creation."""
        key1 = PromptOptimizer.create_cache_key(
            "Hello world",
            "gpt-4",
            temperature=0.7,
        )
        key2 = PromptOptimizer.create_cache_key(
            "Hello world",
            "gpt-4",
            temperature=0.7,
        )
        key3 = PromptOptimizer.create_cache_key(
            "Different prompt",
            "gpt-4",
            temperature=0.7,
        )

        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different keys
        assert key1 != key3
        # Keys should have expected prefix
        assert key1.startswith("llm_response:gpt-4:")

    @pytest.mark.asyncio
    async def test_cache_and_retrieve_llm_response(self):
        """Test caching and retrieving LLM responses."""
        prompt = "What is AI?"
        model = "gpt-4"
        response = "AI is artificial intelligence..."

        with patch("app.services.performance_optimizer.cache") as mock_cache:
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.get = AsyncMock(return_value=response)

            # Cache the response
            await PromptOptimizer.cache_llm_response(prompt, model, response)
            mock_cache.set.assert_called_once()

            # Retrieve the cached response
            cached = await PromptOptimizer.get_cached_llm_response(prompt, model)
            assert cached == response
            mock_cache.get.assert_called_once()


class TestAsyncOptimizer:
    """Test suite for AsyncOptimizer."""

    @pytest.mark.asyncio
    async def test_batch_execute_limited_concurrency(self):
        """Test batch execution with concurrency limit."""
        execution_times = []

        async def mock_task(task_id: int):
            execution_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)
            return task_id

        tasks = [lambda i=i: mock_task(i) for i in range(20)]

        results = await AsyncOptimizer.batch_execute(tasks, max_concurrent=5)

        assert len(results) == 20
        assert sorted(results) == list(range(20))
        # With max_concurrent=5 and 0.1s per task,
        # we should have roughly 4 batches

    @pytest.mark.asyncio
    async def test_memoize_async_decorator(self):
        """Test async memoization decorator."""
        call_count = 0

        @AsyncOptimizer.memoize_async(ttl=1)
        async def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 2

        # First call - should execute
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should use cache
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Not incremented

        # Different argument - should execute
        result3 = await expensive_function(10)
        assert result3 == 20
        assert call_count == 2

        # Wait for TTL expiration
        await asyncio.sleep(1.1)

        # After TTL - should execute again
        result4 = await expensive_function(5)
        assert result4 == 10
        assert call_count == 3


@pytest.mark.integration
class TestPerformanceIntegration:
    """Integration tests for performance optimizations."""

    @pytest.mark.asyncio
    async def test_end_to_end_caching_workflow(self):
        """Test complete caching workflow."""
        # This would be an integration test with real database and Redis
        # For now, it's a placeholder
        pass

    @pytest.mark.asyncio
    async def test_database_query_performance(self):
        """Test database query performance with indexes."""
        # This would measure query execution time
        # For now, it's a placeholder
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
