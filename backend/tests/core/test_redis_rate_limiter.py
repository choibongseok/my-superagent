"""
Tests for Redis-based rate limiter.
"""
import time
import pytest
from unittest.mock import Mock, MagicMock, patch
from redis.exceptions import RedisError

from app.core.redis_rate_limiter import RedisRateLimiter


class TestRedisRateLimiter:
    """Test suite for RedisRateLimiter."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = Mock()
        redis.script_load = Mock(return_value="test_sha")
        return redis
    
    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create rate limiter instance."""
        return RedisRateLimiter(mock_redis)
    
    def test_initialization(self, mock_redis):
        """Test rate limiter initialization."""
        limiter = RedisRateLimiter(mock_redis)
        
        assert limiter.redis == mock_redis
        assert limiter.script_sha == "test_sha"
        mock_redis.script_load.assert_called_once()
    
    def test_initialization_lua_script_failure(self, mock_redis):
        """Test graceful handling of Lua script load failure."""
        mock_redis.script_load.side_effect = RedisError("Connection failed")
        
        limiter = RedisRateLimiter(mock_redis)
        
        assert limiter.script_sha is None
    
    def test_check_rate_limit_allowed(self, rate_limiter, mock_redis):
        """Test rate limit check when request is allowed."""
        mock_redis.evalsha = Mock(return_value=[1, 99])  # Allowed, 99 remaining
        
        allowed, remaining, reset_time = rate_limiter.check_rate_limit(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        assert allowed is True
        assert remaining == 99
        assert reset_time > int(time.time())
        
        # Verify Lua script was called
        mock_redis.evalsha.assert_called_once()
        args = mock_redis.evalsha.call_args
        assert args[0][0] == "test_sha"
        assert args[0][1] == 1  # Number of keys
        assert "rate_limit:user123:/api/test" in args[0][2]
    
    def test_check_rate_limit_denied(self, rate_limiter, mock_redis):
        """Test rate limit check when request is denied."""
        mock_redis.evalsha = Mock(return_value=[0, 0])  # Denied, 0 remaining
        
        allowed, remaining, reset_time = rate_limiter.check_rate_limit(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        assert allowed is False
        assert remaining == 0
        assert reset_time > int(time.time())
    
    def test_check_rate_limit_without_lua_script(self, mock_redis):
        """Test rate limit check using fallback (no Lua script)."""
        mock_redis.script_load.side_effect = RedisError("Not supported")
        limiter = RedisRateLimiter(mock_redis)
        
        # Mock pipeline operations
        pipeline = Mock()
        pipeline.zremrangebyscore = Mock()
        pipeline.zcard = Mock()
        pipeline.zadd = Mock()
        pipeline.expire = Mock()
        pipeline.execute = Mock(return_value=[None, 50, None, None])
        mock_redis.pipeline = Mock(return_value=pipeline)
        
        allowed, remaining, reset_time = limiter.check_rate_limit(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        assert allowed is True
        assert remaining == 49  # 100 - 50 - 1
        pipeline.execute.assert_called_once()
    
    def test_check_rate_limit_redis_failure(self, rate_limiter, mock_redis):
        """Test graceful handling of Redis failure (fail open)."""
        mock_redis.evalsha.side_effect = RedisError("Connection lost")
        
        allowed, remaining, reset_time = rate_limiter.check_rate_limit(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        # Should fail open (allow request)
        assert allowed is True
        assert remaining == 100
    
    def test_get_remaining_quota(self, rate_limiter, mock_redis):
        """Test getting remaining quota without consuming."""
        mock_redis.zremrangebyscore = Mock()
        mock_redis.zcard = Mock(return_value=30)
        
        remaining = rate_limiter.get_remaining_quota(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        assert remaining == 70  # 100 - 30
        mock_redis.zremrangebyscore.assert_called_once()
        mock_redis.zcard.assert_called_once()
    
    def test_get_remaining_quota_redis_failure(self, rate_limiter, mock_redis):
        """Test get_remaining_quota with Redis failure."""
        mock_redis.zremrangebyscore.side_effect = RedisError("Connection lost")
        
        remaining = rate_limiter.get_remaining_quota(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        # Should return full limit on failure
        assert remaining == 100
    
    def test_reset_quota_specific_endpoint(self, rate_limiter, mock_redis):
        """Test resetting quota for specific endpoint."""
        mock_redis.delete = Mock()
        
        rate_limiter.reset_quota(user_id="user123", endpoint="/api/test")
        
        mock_redis.delete.assert_called_once_with("rate_limit:user123:/api/test")
    
    def test_reset_quota_all_endpoints(self, rate_limiter, mock_redis):
        """Test resetting quota for all endpoints."""
        mock_redis.scan_iter = Mock(return_value=[
            "rate_limit:user123:/api/test1",
            "rate_limit:user123:/api/test2"
        ])
        mock_redis.delete = Mock()
        
        rate_limiter.reset_quota(user_id="user123", endpoint=None)
        
        # Should delete all keys matching pattern
        assert mock_redis.delete.call_count == 2
    
    def test_sliding_window_accuracy(self, rate_limiter, mock_redis):
        """Test that sliding window removes old entries correctly."""
        current_time = int(time.time() * 1000)
        window_ms = 60000  # 60 seconds
        
        mock_redis.evalsha = Mock(return_value=[1, 99])
        
        rate_limiter.check_rate_limit(
            user_id="user123",
            endpoint="/api/test",
            limit=100,
            window_seconds=60
        )
        
        # Verify that ZREMRANGEBYSCORE was called in Lua script
        # (by checking that evalsha was called with correct window calculation)
        args = mock_redis.evalsha.call_args[0]
        assert args[3] == 60000  # window_seconds * 1000
    
    def test_concurrent_requests(self, rate_limiter, mock_redis):
        """Test handling of concurrent requests."""
        # Simulate race condition - both requests check at same time
        call_count = [0]
        
        def mock_evalsha(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return [1, 99]  # First request: allowed
            else:
                return [1, 98]  # Second request: allowed
        
        mock_redis.evalsha = Mock(side_effect=mock_evalsha)
        
        # Make two rapid requests
        result1 = rate_limiter.check_rate_limit("user123", "/api/test", 100, 60)
        result2 = rate_limiter.check_rate_limit("user123", "/api/test", 100, 60)
        
        assert result1[0] is True
        assert result2[0] is True
        assert result1[1] > result2[1]  # Second request should have fewer remaining
    
    def test_multiple_users_isolated(self, rate_limiter, mock_redis):
        """Test that different users have isolated quotas."""
        mock_redis.evalsha = Mock(return_value=[1, 99])
        
        # User 1
        rate_limiter.check_rate_limit("user1", "/api/test", 100, 60)
        
        # User 2
        rate_limiter.check_rate_limit("user2", "/api/test", 100, 60)
        
        # Should have separate keys
        calls = mock_redis.evalsha.call_args_list
        assert "rate_limit:user1:/api/test" in calls[0][0][2]
        assert "rate_limit:user2:/api/test" in calls[1][0][2]
    
    def test_multiple_endpoints_isolated(self, rate_limiter, mock_redis):
        """Test that different endpoints have isolated quotas."""
        mock_redis.evalsha = Mock(return_value=[1, 99])
        
        # Endpoint 1
        rate_limiter.check_rate_limit("user1", "/api/endpoint1", 100, 60)
        
        # Endpoint 2
        rate_limiter.check_rate_limit("user1", "/api/endpoint2", 100, 60)
        
        # Should have separate keys
        calls = mock_redis.evalsha.call_args_list
        assert "/api/endpoint1" in calls[0][0][2]
        assert "/api/endpoint2" in calls[1][0][2]
