# Phase 5 Implementation Guide: Scale & Performance

> **목표**: 엔터프라이즈급 성능 및 확장성 확보
> **기간**: 2주
> **우선순위**: P0 (Critical)

---

## Overview

Phase 5는 AgentHQ의 성능 최적화 및 대규모 확장성을 확보합니다.

### Key Features
- ✅ **Query Optimization**: Database 쿼리 최적화
- ✅ **Connection Pooling**: DB 연결 풀링
- ✅ **Caching Strategy**: Redis 캐싱 전략
- ✅ **CDN Integration**: 정적 자산 CDN 배포
- ✅ **Load Balancing**: 서버 로드 밸런싱
- ✅ **Horizontal Scaling**: Auto-scaling 설정

---

## Performance Targets

### API Performance
| Metric | Target | Current |
|--------|--------|---------|
| API Response Time (P95) | < 200ms | TBD |
| API Response Time (P99) | < 500ms | TBD |
| Throughput | 10,000 req/s | TBD |

### Task Processing
| Metric | Target | Current |
|--------|--------|---------|
| Task Processing Time (P95) | < 30s | TBD |
| Task Success Rate | 99%+ | TBD |
| Concurrent Tasks | 1000+ | TBD |

### System Resources
| Metric | Target | Current |
|--------|--------|---------|
| Database Connections | < 100 | TBD |
| Memory Usage | < 2GB/instance | TBD |
| CPU Usage | < 70% | TBD |

---

## Implementation

### 1. Database Optimization

#### Connection Pooling

**File**: `backend/app/core/database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

# Optimized connection pool
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=QueuePool,
    pool_size=20,              # Base connections
    max_overflow=10,           # Additional connections
    pool_pre_ping=True,        # Verify connections
    pool_recycle=3600,         # Recycle after 1 hour
    pool_timeout=30,           # Timeout for connection
)
```

#### Query Optimization

```python
# Bad: N+1 query problem
users = await session.execute(select(User))
for user in users:
    tasks = await session.execute(
        select(Task).where(Task.user_id == user.id)
    )

# Good: Join eagerly
users = await session.execute(
    select(User)
    .options(selectinload(User.tasks))
)
```

#### Indexing Strategy

```sql
-- Add indexes for frequently queried fields
CREATE INDEX CONCURRENTLY idx_tasks_user_status 
    ON tasks(user_id, status);

CREATE INDEX CONCURRENTLY idx_tasks_created_at 
    ON tasks(created_at DESC);

CREATE INDEX CONCURRENTLY idx_activity_logs_team_date 
    ON activity_logs(team_id, created_at DESC);

-- Composite index for common queries
CREATE INDEX CONCURRENTLY idx_tasks_composite 
    ON tasks(user_id, status, created_at DESC);
```

### 2. Redis Caching

**File**: `backend/app/core/cache.py`

```python
import redis.asyncio as redis
from typing import Optional, Any
import json
import pickle

class CacheManager:
    """Redis cache manager"""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=False
        )

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = await self.redis.get(key)
        if value:
            return pickle.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300  # 5 minutes default
    ):
        """Set value in cache"""
        serialized = pickle.dumps(value)
        await self.redis.setex(key, ttl, serialized)

    async def delete(self, key: str):
        """Delete key from cache"""
        await self.redis.delete(key)

    async def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern"""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

# Cache decorators
def cached(ttl: int = 300, key_prefix: str = ""):
    """Cache decorator for functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{kwargs}"

            # Try cache first
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            await cache_manager.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator
```

**Usage**:

```python
@cached(ttl=600, key_prefix="user")
async def get_user_by_id(user_id: UUID) -> Optional[User]:
    """Get user with 10-minute cache"""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
```

### 3. API Response Caching

**File**: `backend/app/middleware/cache_middleware.py`

```python
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib

class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """Cache GET responses"""

    def __init__(self, app, cache_manager):
        super().__init__(app)
        self.cache = cache_manager

    async def dispatch(self, request: Request, call_next):
        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        # Generate cache key
        cache_key = self._generate_key(request)

        # Try cache
        cached_response = await self.cache.get(cache_key)
        if cached_response:
            return Response(
                content=cached_response['body'],
                status_code=cached_response['status_code'],
                headers=cached_response['headers']
            )

        # Execute request
        response = await call_next(request)

        # Cache successful responses
        if response.status_code == 200:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            await self.cache.set(
                cache_key,
                {
                    'body': body,
                    'status_code': response.status_code,
                    'headers': dict(response.headers)
                },
                ttl=60  # 1 minute
            )

            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

        return response

    def _generate_key(self, request: Request) -> str:
        """Generate cache key from request"""
        key_parts = [
            request.url.path,
            str(request.query_params),
            request.headers.get('authorization', '')
        ]
        key_string = ":".join(key_parts)
        return f"response:{hashlib.md5(key_string.encode()).hexdigest()}"
```

### 4. Celery Optimization

**File**: `backend/app/workers/celery_config.py`

```python
from celery import Celery

celery_app = Celery(
    "agenthq",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Optimized configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Performance settings
    worker_prefetch_multiplier=4,    # Prefetch 4 tasks
    worker_max_tasks_per_child=1000, # Recycle worker after 1000 tasks
    task_acks_late=True,             # Ack after task completion
    task_reject_on_worker_lost=True, # Retry if worker dies

    # Concurrency
    worker_concurrency=10,           # 10 concurrent tasks

    # Result backend
    result_backend_transport_options={
        'master_name': 'mymaster',
    },
    result_expires=3600,             # Results expire after 1 hour

    # Rate limiting
    task_default_rate_limit='100/m', # 100 tasks per minute
)
```

### 5. Load Balancing & Auto-scaling

#### Nginx Configuration

**File**: `nginx.conf`

```nginx
upstream backend {
    least_conn;
    server backend1:8000 weight=1;
    server backend2:8000 weight=1;
    server backend3:8000 weight=1;
}

server {
    listen 80;
    server_name api.agenthq.com;

    # Gzip compression
    gzip on;
    gzip_types text/plain application/json;
    gzip_min_length 1000;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req zone=api burst=20 nodelay;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;

        # Keep-alive
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

#### Kubernetes Auto-scaling

**File**: `k8s/hpa.yaml`

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
      - type: Pods
        value: 5
        periodSeconds: 30
      selectPolicy: Max
```

### 6. Monitoring & Alerting

**File**: `backend/app/middleware/metrics_middleware.py`

```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

active_requests = Gauge(
    'http_requests_active',
    'Active HTTP requests'
)

class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect metrics for monitoring"""

    async def dispatch(self, request: Request, call_next):
        active_requests.inc()
        start_time = time.time()

        try:
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            request_duration.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

            request_count.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()

            return response

        finally:
            active_requests.dec()
```

---

## Testing

### Load Testing

```python
# Use Locust for load testing
from locust import HttpUser, task, between

class AgentHQUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def get_tasks(self):
        self.client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {self.token}"})

    @task(1)
    def create_task(self):
        self.client.post(
            "/api/v1/tasks",
            json={
                "prompt": "Test task",
                "output_type": "docs"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
```

Run load test:
```bash
locust -f locustfile.py --host=http://localhost:8000 --users=1000 --spawn-rate=10
```

### Performance Benchmarks

```bash
# API benchmarks
ab -n 10000 -c 100 http://localhost:8000/api/v1/tasks

# Database query benchmarks
EXPLAIN ANALYZE SELECT * FROM tasks WHERE user_id = '...';
```

---

## Success Criteria

### Performance Metrics
- ✅ API P95 < 200ms
- ✅ API P99 < 500ms
- ✅ Task processing < 30s
- ✅ 10,000+ concurrent users
- ✅ 99.9% uptime

### Scalability
- ✅ Horizontal scaling to 20+ instances
- ✅ Database connection pooling working
- ✅ Redis caching reducing load 50%+
- ✅ Auto-scaling based on load

---

## Next Steps

- **Phase 6**: Advanced features (Plugin system, Templates)
- **Optimization**: Continuous performance monitoring
- **Cost**: Cloud cost optimization

---

## References

- [FastAPI Performance](https://fastapi.tiangolo.com/deployment/concepts/)
- [PostgreSQL Performance](https://www.postgresql.org/docs/current/performance-tips.html)
- [Redis Best Practices](https://redis.io/docs/manual/patterns/)
- [PHASE_PLAN.md](PHASE_PLAN.md)
