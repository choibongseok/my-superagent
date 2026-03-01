"""
Redis-based distributed rate limiter with sliding window algorithm.
"""
import time
from typing import Optional, Tuple
from redis import Redis
from redis.exceptions import RedisError
import logging

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis for token bucket/sliding window.
    
    Features:
    - Sliding window algorithm for accurate rate limiting
    - Atomic operations with Lua scripts
    - Graceful degradation if Redis unavailable
    - Per-user and per-endpoint rate limiting
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        
        # Lua script for atomic rate limiting with sliding window
        self.lua_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local current_time = tonumber(ARGV[3])
        
        -- Remove old entries outside the window
        redis.call('ZREMRANGEBYSCORE', key, 0, current_time - window)
        
        -- Count current requests in window
        local current_count = redis.call('ZCARD', key)
        
        if current_count < limit then
            -- Add current request
            redis.call('ZADD', key, current_time, current_time)
            redis.call('EXPIRE', key, window)
            return {1, limit - current_count - 1}
        else
            return {0, 0}
        end
        """
        
        try:
            self.script_sha = self.redis.script_load(self.lua_script)
        except RedisError as e:
            logger.warning(f"Failed to load rate limit Lua script: {e}")
            self.script_sha = None
    
    def check_rate_limit(
        self,
        user_id: str,
        endpoint: str,
        limit: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int, int]:
        """
        Check if request should be allowed under rate limit.
        
        Args:
            user_id: User identifier
            endpoint: API endpoint path
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)
        
        Returns:
            Tuple of (allowed, remaining, reset_time):
            - allowed: True if request is allowed
            - remaining: Number of remaining requests in window
            - reset_time: Unix timestamp when quota resets
        """
        key = f"rate_limit:{user_id}:{endpoint}"
        current_time = int(time.time() * 1000)  # Milliseconds for precision
        reset_time = int(time.time()) + window_seconds
        
        try:
            if self.script_sha:
                # Use Lua script for atomic operation
                result = self.redis.evalsha(
                    self.script_sha,
                    1,
                    key,
                    limit,
                    window_seconds * 1000,  # Convert to milliseconds
                    current_time
                )
                allowed = bool(result[0])
                remaining = int(result[1])
            else:
                # Fallback to regular commands (not atomic, but works)
                pipe = self.redis.pipeline()
                pipe.zremrangebyscore(key, 0, current_time - (window_seconds * 1000))
                pipe.zcard(key)
                pipe.zadd(key, {str(current_time): current_time})
                pipe.expire(key, window_seconds)
                _, current_count, _, _ = pipe.execute()
                
                allowed = current_count < limit
                remaining = max(0, limit - current_count - 1) if allowed else 0
            
            return allowed, remaining, reset_time
            
        except RedisError as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fail open - allow request if Redis is down
            return True, limit, reset_time
    
    def get_remaining_quota(
        self,
        user_id: str,
        endpoint: str,
        limit: int,
        window_seconds: int = 60
    ) -> int:
        """
        Get remaining quota without consuming it.
        
        Args:
            user_id: User identifier
            endpoint: API endpoint path
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
        
        Returns:
            Number of remaining requests in current window
        """
        key = f"rate_limit:{user_id}:{endpoint}"
        current_time = int(time.time() * 1000)
        
        try:
            # Remove expired entries
            self.redis.zremrangebyscore(key, 0, current_time - (window_seconds * 1000))
            
            # Count current requests
            current_count = self.redis.zcard(key)
            
            return max(0, limit - current_count)
            
        except RedisError as e:
            logger.error(f"Failed to get remaining quota: {e}")
            return limit  # Fail open
    
    def reset_quota(self, user_id: str, endpoint: Optional[str] = None):
        """
        Reset rate limit quota for user (admin override).
        
        Args:
            user_id: User identifier
            endpoint: Specific endpoint to reset, or None for all
        """
        try:
            if endpoint:
                key = f"rate_limit:{user_id}:{endpoint}"
                self.redis.delete(key)
            else:
                # Delete all rate limit keys for user
                pattern = f"rate_limit:{user_id}:*"
                for key in self.redis.scan_iter(match=pattern):
                    self.redis.delete(key)
                    
        except RedisError as e:
            logger.error(f"Failed to reset quota: {e}")


# Global rate limiter instance (initialized in main.py)
rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> Optional[RedisRateLimiter]:
    """Get global rate limiter instance."""
    return rate_limiter


def init_rate_limiter(redis_client: Redis):
    """Initialize global rate limiter."""
    global rate_limiter
    rate_limiter = RedisRateLimiter(redis_client)
