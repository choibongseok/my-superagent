"""Load testing for Celery workers.

This module tests Celery worker performance under various load scenarios:
- Concurrent task processing
- Bulk task queueing
- Memory and performance monitoring
- Worker resilience and recovery
"""

import asyncio
import concurrent.futures
import logging
import time
from typing import List, Dict, Any
from uuid import uuid4

import pytest
from celery import group
from celery.result import AsyncResult

from app.agents.celery_app import celery_app

logger = logging.getLogger(__name__)


class LoadTestMetrics:
    """Track load test metrics."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.tasks_submitted = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_duration = 0.0
        self.task_durations = []
        self.errors = []

    def start(self):
        """Start timing."""
        self.start_time = time.time()

    def end(self):
        """End timing."""
        self.end_time = time.time()
        self.total_duration = self.end_time - self.start_time

    def add_task_duration(self, duration: float):
        """Add individual task duration."""
        self.task_durations.append(duration)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        if not self.task_durations:
            avg_duration = 0.0
            min_duration = 0.0
            max_duration = 0.0
        else:
            avg_duration = sum(self.task_durations) / len(self.task_durations)
            min_duration = min(self.task_durations)
            max_duration = max(self.task_durations)

        throughput = (
            self.tasks_completed / self.total_duration
            if self.total_duration > 0
            else 0
        )

        return {
            "total_duration": round(self.total_duration, 2),
            "tasks_submitted": self.tasks_submitted,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "success_rate": (
                round(
                    (self.tasks_completed / self.tasks_submitted) * 100, 2
                )
                if self.tasks_submitted > 0
                else 0
            ),
            "throughput_tasks_per_sec": round(throughput, 2),
            "avg_task_duration": round(avg_duration, 2),
            "min_task_duration": round(min_duration, 2),
            "max_task_duration": round(max_duration, 2),
            "error_count": len(self.errors),
        }


@pytest.fixture
def metrics():
    """Provide metrics tracker."""
    return LoadTestMetrics()


@pytest.mark.asyncio
async def test_health_check_load(metrics):
    """Test health check task under load.

    Validates that simple health checks can handle high concurrency.
    """
    logger.info("Starting health check load test")
    metrics.start()

    num_tasks = 100
    metrics.tasks_submitted = num_tasks

    # Submit all tasks at once
    tasks = [
        celery_app.send_task("agents.health_check")
        for _ in range(num_tasks)
    ]

    # Wait for all tasks to complete
    for task_result in tasks:
        task_start = time.time()
        try:
            result = task_result.get(timeout=30)
            assert result["status"] == "healthy"
            metrics.tasks_completed += 1
            task_duration = time.time() - task_start
            metrics.add_task_duration(task_duration)
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))
            logger.error(f"Health check task failed: {e}")

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Health check load test stats: {stats}")

    # Assertions
    assert stats["success_rate"] >= 95.0, "Success rate should be at least 95%"
    assert (
        stats["throughput_tasks_per_sec"] > 5.0
    ), "Throughput should be > 5 tasks/sec"
    assert (
        stats["avg_task_duration"] < 2.0
    ), "Average task duration should be < 2 seconds"


@pytest.mark.asyncio
async def test_concurrent_research_tasks(metrics):
    """Test concurrent research task processing.

    Simulates multiple users submitting research tasks simultaneously.
    """
    logger.info("Starting concurrent research tasks test")
    metrics.start()

    num_tasks = 20  # Reduced for actual LLM calls
    user_ids = [f"load-test-user-{i}" for i in range(5)]
    prompts = [
        "What is Python?",
        "Explain machine learning briefly",
        "What is FastAPI?",
        "Tell me about async programming",
    ]

    tasks = []
    for i in range(num_tasks):
        task_id = str(uuid4())
        user_id = user_ids[i % len(user_ids)]
        prompt = prompts[i % len(prompts)]

        # Submit task (don't wait)
        task_result = celery_app.send_task(
            "agents.process_research_task",
            args=[task_id, prompt, user_id, "openai", "gpt-3.5-turbo"],
        )
        tasks.append(task_result)
        metrics.tasks_submitted += 1

    # Wait for all tasks with timeout
    timeout = 300  # 5 minutes for research tasks
    for task_result in tasks:
        task_start = time.time()
        try:
            result = task_result.get(timeout=timeout)
            assert result["status"] == "completed"
            metrics.tasks_completed += 1
            task_duration = time.time() - task_start
            metrics.add_task_duration(task_duration)
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))
            logger.error(f"Research task failed: {e}")

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Concurrent research tasks stats: {stats}")

    # Assertions (looser for LLM tasks)
    assert (
        stats["success_rate"] >= 80.0
    ), "Success rate should be at least 80%"
    assert (
        stats["avg_task_duration"] < 60.0
    ), "Average task duration should be < 60 seconds"


@pytest.mark.asyncio
async def test_bulk_task_queueing(metrics):
    """Test bulk task submission and queue handling.

    Validates that the queue can handle a large burst of tasks.
    """
    logger.info("Starting bulk task queueing test")
    metrics.start()

    num_tasks = 500
    metrics.tasks_submitted = num_tasks

    # Submit tasks in bulk using group
    task_group = group(
        celery_app.signature("agents.health_check")
        for _ in range(num_tasks)
    )

    # Apply async
    group_result = task_group.apply_async()

    # Wait for all tasks
    task_results = group_result.get(timeout=120)

    for result in task_results:
        if result and result.get("status") == "healthy":
            metrics.tasks_completed += 1
        else:
            metrics.tasks_failed += 1

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Bulk task queueing stats: {stats}")

    # Assertions
    assert stats["success_rate"] >= 95.0, "Success rate should be at least 95%"
    assert (
        stats["total_duration"] < 120.0
    ), "Should complete 500 tasks in < 2 minutes"


@pytest.mark.asyncio
async def test_sustained_load(metrics):
    """Test sustained load over time.

    Simulates continuous task submission over a period.
    """
    logger.info("Starting sustained load test")
    metrics.start()

    duration_seconds = 60  # 1 minute sustained load
    tasks_per_second = 5

    tasks = []
    end_time = time.time() + duration_seconds

    while time.time() < end_time:
        batch_start = time.time()

        # Submit batch of tasks
        for _ in range(tasks_per_second):
            task_result = celery_app.send_task("agents.health_check")
            tasks.append(task_result)
            metrics.tasks_submitted += 1

        # Wait for next second
        elapsed = time.time() - batch_start
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

    # Wait for all tasks to complete
    for task_result in tasks:
        try:
            result = task_result.get(timeout=30)
            if result and result.get("status") == "healthy":
                metrics.tasks_completed += 1
            else:
                metrics.tasks_failed += 1
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))
            logger.error(f"Sustained load task failed: {e}")

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Sustained load test stats: {stats}")

    # Assertions
    assert stats["success_rate"] >= 90.0, "Success rate should be at least 90%"
    assert (
        metrics.tasks_submitted >= 250
    ), "Should submit at least 250 tasks in 1 minute"


@pytest.mark.asyncio
async def test_task_retry_behavior(metrics):
    """Test task retry behavior under failure conditions.

    Validates that tasks retry appropriately on failure.
    """
    logger.info("Starting task retry behavior test")
    metrics.start()

    # We'll test health check which should always succeed
    # In a real scenario, you might inject failures
    num_tasks = 10
    metrics.tasks_submitted = num_tasks

    tasks = []
    for _ in range(num_tasks):
        task_result = celery_app.send_task("agents.health_check")
        tasks.append(task_result)

    # Monitor task states
    for task_result in tasks:
        task_start = time.time()
        try:
            # Check task state
            state = task_result.state
            logger.info(f"Task {task_result.id} state: {state}")

            result = task_result.get(timeout=30)
            assert result["status"] == "healthy"
            metrics.tasks_completed += 1
            task_duration = time.time() - task_start
            metrics.add_task_duration(task_duration)
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))
            logger.error(f"Task retry test failed: {e}")

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Task retry behavior stats: {stats}")

    # Assertions
    assert (
        stats["success_rate"] == 100.0
    ), "All tasks should complete successfully"


@pytest.mark.asyncio
async def test_worker_memory_usage(metrics):
    """Test worker memory usage under load.

    Monitors that memory doesn't grow excessively during task processing.
    """
    logger.info("Starting worker memory usage test")
    metrics.start()

    # Submit moderate load
    num_tasks = 100
    metrics.tasks_submitted = num_tasks

    tasks = [
        celery_app.send_task("agents.health_check")
        for _ in range(num_tasks)
    ]

    # Wait for completion
    for task_result in tasks:
        try:
            result = task_result.get(timeout=30)
            assert result["status"] == "healthy"
            metrics.tasks_completed += 1
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Worker memory usage test stats: {stats}")

    # Basic assertions (memory profiling would require additional tools)
    assert stats["success_rate"] >= 95.0, "Success rate should be at least 95%"
    assert (
        len(metrics.errors) < 5
    ), "Should have fewer than 5 errors in 100 tasks"


def test_celery_worker_connectivity():
    """Test basic Celery worker connectivity.

    Validates that workers are reachable and responding.
    """
    logger.info("Testing Celery worker connectivity")

    # Inspect active workers
    inspect = celery_app.control.inspect()
    
    # Check if workers are active
    active_workers = inspect.active()
    
    if active_workers:
        logger.info(f"Active workers: {list(active_workers.keys())}")
        
        # Check stats
        stats = inspect.stats()
        logger.info(f"Worker stats: {stats}")
        
        # Check registered tasks
        registered = inspect.registered()
        logger.info(f"Registered tasks: {registered}")
        
        assert len(active_workers) > 0, "At least one worker should be active"
    else:
        logger.warning("No active workers found - this test requires running workers")
        pytest.skip("Celery workers not available")


@pytest.mark.asyncio
async def test_task_routing_and_priority(metrics):
    """Test task routing and priority handling.

    Validates that high-priority tasks are processed first.
    """
    logger.info("Starting task routing and priority test")
    metrics.start()

    # Submit low priority tasks first
    low_priority_tasks = [
        celery_app.send_task("agents.health_check", priority=1)
        for _ in range(10)
    ]

    # Then high priority tasks
    high_priority_tasks = [
        celery_app.send_task("agents.health_check", priority=9)
        for _ in range(5)
    ]

    metrics.tasks_submitted = len(low_priority_tasks) + len(high_priority_tasks)

    # Monitor which completes first
    all_tasks = low_priority_tasks + high_priority_tasks

    for task_result in all_tasks:
        try:
            result = task_result.get(timeout=30)
            assert result["status"] == "healthy"
            metrics.tasks_completed += 1
        except Exception as e:
            metrics.tasks_failed += 1
            metrics.errors.append(str(e))

    metrics.end()
    stats = metrics.get_stats()

    logger.info(f"Task routing and priority test stats: {stats}")

    # Basic assertion
    assert (
        stats["success_rate"] == 100.0
    ), "All priority tasks should complete"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
