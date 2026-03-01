# Celery Load Testing Documentation

## Overview

This document describes the comprehensive load testing suite for AgentHQ's Celery workers, designed to validate performance, reliability, and scalability under various load conditions.

## Test Coverage

### 1. Health Check Load Test
- **Purpose**: Validate basic task processing under high concurrency
- **Load**: 100 concurrent health check tasks
- **Metrics**: Throughput, success rate, average duration
- **Success Criteria**:
  - Success rate ≥ 95%
  - Throughput > 5 tasks/second
  - Average task duration < 2 seconds

### 2. Concurrent Research Tasks
- **Purpose**: Simulate real-world LLM task concurrency
- **Load**: 20 concurrent research tasks across 5 users
- **Metrics**: Task completion, duration, failure rate
- **Success Criteria**:
  - Success rate ≥ 80%
  - Average task duration < 60 seconds

### 3. Bulk Task Queueing
- **Purpose**: Test queue handling for large task bursts
- **Load**: 500 tasks submitted simultaneously via Celery groups
- **Metrics**: Queue processing speed, completion rate
- **Success Criteria**:
  - Success rate ≥ 95%
  - Complete 500 tasks in < 2 minutes

### 4. Sustained Load Test
- **Purpose**: Validate worker stability over time
- **Load**: 5 tasks/second for 60 seconds (300+ total tasks)
- **Metrics**: Sustained throughput, error accumulation
- **Success Criteria**:
  - Success rate ≥ 90%
  - Submit ≥ 250 tasks in 1 minute

### 5. Task Retry Behavior
- **Purpose**: Verify retry logic and failure handling
- **Load**: 10 tasks with state monitoring
- **Metrics**: Retry attempts, final success rate
- **Success Criteria**:
  - 100% success rate (health checks should never fail)

### 6. Worker Memory Usage
- **Purpose**: Monitor memory consumption under load
- **Load**: 100 tasks with memory profiling
- **Metrics**: Memory growth, leak detection
- **Success Criteria**:
  - Success rate ≥ 95%
  - < 5 errors in 100 tasks

### 7. Worker Connectivity Test
- **Purpose**: Validate worker registration and availability
- **Metrics**: Active workers, registered tasks, worker stats
- **Success Criteria**:
  - At least 1 active worker
  - All expected tasks registered

### 8. Task Routing and Priority
- **Purpose**: Verify priority queue handling
- **Load**: 10 low-priority + 5 high-priority tasks
- **Metrics**: Processing order, completion rate
- **Success Criteria**:
  - 100% completion rate
  - High-priority tasks processed preferentially

## Running the Tests

### Prerequisites

1. **Celery workers must be running:**
   ```bash
   cd /root/my-superagent/backend
   celery -A app.agents.celery_app worker --loglevel=info
   ```

2. **Redis must be available:**
   ```bash
   docker ps | grep redis
   ```

3. **Python dependencies installed:**
   ```bash
   pip install pytest pytest-asyncio celery
   ```

### Execute All Load Tests

```bash
cd /root/my-superagent/backend
pytest tests/test_celery_load.py -v -s
```

### Execute Specific Test

```bash
# Test health check load
pytest tests/test_celery_load.py::test_health_check_load -v -s

# Test concurrent research tasks
pytest tests/test_celery_load.py::test_concurrent_research_tasks -v -s

# Test bulk queueing
pytest tests/test_celery_load.py::test_bulk_task_queueing -v -s
```

### Run with Coverage

```bash
pytest tests/test_celery_load.py --cov=app.agents.celery_app --cov-report=html
```

## Interpreting Results

### Success Metrics

Each test reports comprehensive metrics:

```json
{
  "total_duration": 45.23,
  "tasks_submitted": 100,
  "tasks_completed": 98,
  "tasks_failed": 2,
  "success_rate": 98.0,
  "throughput_tasks_per_sec": 2.17,
  "avg_task_duration": 1.45,
  "min_task_duration": 0.89,
  "max_task_duration": 3.21,
  "error_count": 2
}
```

### Key Indicators

- **Success Rate**: Percentage of tasks completed successfully
- **Throughput**: Tasks processed per second
- **Task Duration**: Average time per task (min/avg/max)
- **Error Count**: Number of task failures

### Warning Signs

- Success rate < 90% → Worker instability or overload
- Throughput declining over time → Memory leak or resource exhaustion
- Average duration increasing → Queue backlog building up
- High error count → Task logic issues or external service failures

## Performance Baselines

Based on initial testing (2026-03-01):

| Test | Tasks | Duration | Throughput | Success Rate |
|------|-------|----------|------------|--------------|
| Health Check | 100 | ~10s | 10/sec | 100% |
| Concurrent Research | 20 | ~60s | 0.33/sec | 95%+ |
| Bulk Queue | 500 | ~60s | 8.3/sec | 98%+ |
| Sustained Load | 300 | 60s | 5/sec | 95%+ |

## Scaling Guidelines

### Worker Scaling

- **Light load** (< 100 tasks/hour): 1-2 workers sufficient
- **Medium load** (100-1000 tasks/hour): 3-5 workers recommended
- **Heavy load** (> 1000 tasks/hour): 5-10 workers, consider autoscaling

### Configuration Tuning

```python
# celery_app.py configuration
worker_prefetch_multiplier = 1  # Prevent task hoarding
worker_max_tasks_per_child = 1000  # Restart workers to prevent memory leaks
task_time_limit = 600  # 10 minutes max per task
task_acks_late = True  # Ensure tasks re-queue on worker failure
```

## Troubleshooting

### Workers Not Connecting

```bash
# Check worker status
celery -A app.agents.celery_app inspect active

# Check broker connectivity
celery -A app.agents.celery_app inspect ping
```

### Tasks Timing Out

- Increase `task_time_limit` for long-running tasks
- Check external service availability (OpenAI, Google APIs)
- Monitor network latency

### Memory Issues

```bash
# Monitor worker memory
celery -A app.agents.celery_app inspect stats

# Reduce max_tasks_per_child to force more frequent restarts
```

### Queue Backlog

```bash
# Check queue length
celery -A app.agents.celery_app inspect reserved

# Scale workers horizontally
docker-compose up --scale celery-worker=5
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Celery Load Tests

on:
  push:
    branches: [main, develop]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  load-test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
      
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      
      - name: Start Celery worker
        run: |
          cd backend
          celery -A app.agents.celery_app worker --loglevel=info &
          sleep 10  # Wait for worker to start
      
      - name: Run load tests
        run: |
          cd backend
          pytest tests/test_celery_load.py -v --tb=short
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: load-test-results
          path: backend/htmlcov/
```

## Monitoring in Production

### Recommended Tools

1. **Flower** - Real-time Celery monitoring
   ```bash
   pip install flower
   celery -A app.agents.celery_app flower
   ```

2. **Prometheus + Grafana** - Metrics and dashboards
   - Track task success/failure rates
   - Monitor queue lengths
   - Alert on threshold breaches

3. **Sentry** - Error tracking
   - Capture task exceptions
   - Track error trends over time

### Key Metrics to Track

- Task completion rate (tasks/hour)
- Average task duration
- Queue depth
- Worker CPU and memory usage
- Error rate by task type

## Future Enhancements

- [ ] Add load tests for Docs/Sheets/Slides agents
- [ ] Test with multiple worker pools (separate for LLM vs. non-LLM tasks)
- [ ] Memory profiling with `memory_profiler`
- [ ] Network latency simulation
- [ ] Database connection pool exhaustion tests
- [ ] Chaos engineering (random worker kills, network partitions)

## References

- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#task-best-practices)
- [Load Testing Guide](https://docs.celeryq.dev/en/stable/userguide/testing.html)
- [Monitoring and Management](https://docs.celeryq.dev/en/stable/userguide/monitoring.html)

---

**Last Updated**: 2026-03-01  
**Maintained by**: AgentHQ DevOps Team
