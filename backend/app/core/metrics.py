"""Prometheus metrics configuration."""

from prometheus_client import Counter, Gauge, Histogram, Info
from prometheus_client import make_asgi_app

# Application Info
app_info = Info("agenthq_app", "AgentHQ Application Information")

# System Metrics
cpu_usage = Gauge("system_cpu_usage_percent", "CPU usage percentage")
memory_usage = Gauge("system_memory_usage_bytes", "Memory usage in bytes")
memory_usage_percent = Gauge(
    "system_memory_usage_percent", "Memory usage percentage"
)
disk_usage = Gauge("system_disk_usage_bytes", "Disk usage in bytes")
disk_usage_percent = Gauge("system_disk_usage_percent", "Disk usage percentage")

# API Performance Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)

http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint"],
    buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
)

# Database Metrics
db_connections_total = Gauge(
    "db_connections_total", "Total database connections", ["state"]
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

db_queries_total = Counter(
    "db_queries_total", "Total database queries", ["operation", "status"]
)

# Cache Metrics
cache_hits_total = Counter("cache_hits_total", "Total cache hits", ["cache_type"])
cache_misses_total = Counter(
    "cache_misses_total", "Total cache misses", ["cache_type"]
)
cache_size_bytes = Gauge("cache_size_bytes", "Cache size in bytes", ["cache_type"])
cache_evictions_total = Counter(
    "cache_evictions_total", "Total cache evictions", ["cache_type"]
)

# WebSocket Metrics
websocket_connections_active = Gauge(
    "websocket_connections_active", "Active WebSocket connections"
)

websocket_messages_sent_total = Counter(
    "websocket_messages_sent_total", "Total WebSocket messages sent", ["message_type"]
)

websocket_messages_received_total = Counter(
    "websocket_messages_received_total",
    "Total WebSocket messages received",
    ["message_type"],
)

# Task Queue Metrics
task_queue_size = Gauge("task_queue_size", "Task queue size", ["queue_name"])

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task duration in seconds",
    ["task_type", "status"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

tasks_total = Counter(
    "tasks_total", "Total tasks processed", ["task_type", "status"]
)

# LLM Metrics
llm_requests_total = Counter(
    "llm_requests_total", "Total LLM requests", ["provider", "model"]
)

llm_tokens_used_total = Counter(
    "llm_tokens_used_total",
    "Total LLM tokens used",
    ["provider", "model", "token_type"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["provider", "model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

llm_cost_dollars = Counter(
    "llm_cost_dollars", "Total LLM cost in dollars", ["provider", "model"]
)

# User Activity Metrics
active_users_total = Gauge("active_users_total", "Total active users")
user_sessions_active = Gauge("user_sessions_active", "Active user sessions")

user_actions_total = Counter(
    "user_actions_total", "Total user actions", ["action_type"]
)

# Rate Limiting Metrics
rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total rate limited requests",
    ["client_type"],
)

rate_limit_tokens_remaining = Gauge(
    "rate_limit_tokens_remaining",
    "Rate limit tokens remaining",
    ["client_id"],
)

# Business Metrics
chats_created_total = Counter("chats_created_total", "Total chats created")
messages_sent_total = Counter(
    "messages_sent_total", "Total messages sent", ["role"]
)
documents_created_total = Counter(
    "documents_created_total", "Total documents created", ["document_type"]
)

# Create metrics app
metrics_app = make_asgi_app()


def init_metrics():
    """Initialize metrics with default values."""
    app_info.info(
        {
            "version": "0.1.0",
            "environment": "development",
        }
    )

    # Initialize connection state gauges
    db_connections_total.labels(state="idle").set(0)
    db_connections_total.labels(state="active").set(0)
    db_connections_total.labels(state="total").set(0)

    # Initialize cache metrics
    for cache_type in ["api_response", "user_session", "query_result"]:
        cache_size_bytes.labels(cache_type=cache_type).set(0)

    # Initialize WebSocket metrics
    websocket_connections_active.set(0)

    # Initialize user metrics
    active_users_total.set(0)
    user_sessions_active.set(0)
