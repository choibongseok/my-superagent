# 📊 Monitoring Dashboard

**Status**: ✅ Implemented (Sprint 11)  
**Version**: 1.0.0  
**Last Updated**: 2026-03-02

---

## Overview

The Monitoring Dashboard provides real-time insights into AgentHQ's performance, health, and operational status. It includes agent-level metrics, system-wide statistics, error tracking, performance trends, and automated alerts.

### Key Features

- 📈 **Real-time Metrics**: Live system and agent performance data
- 🤖 **Agent Status**: Individual agent health and success rates
- ⚠️ **Error Tracking**: Grouped error summaries with affected agents
- 📊 **Performance Trends**: Time-series data for visualization
- 🚨 **Automated Alerts**: Smart notifications for issues
- 💰 **Cost Tracking**: Integration with budget monitoring
- 🔄 **Workflow Monitoring**: Track multi-agent workflow execution

---

## API Endpoints

All endpoints require authentication except `/monitoring/health`.

### 1. Complete Dashboard

**GET** `/api/v1/monitoring/dashboard`

Returns comprehensive monitoring data including system metrics, agent statuses, errors, trends, and alerts.

**Query Parameters:**
- `hours` (optional, default: 24): Time window in hours (1-168)

**Response:**
```json
{
  "system_metrics": {
    "total_tasks": 1250,
    "active_tasks": 5,
    "completed_tasks": 1200,
    "failed_tasks": 45,
    "avg_task_duration_seconds": 12.5,
    "tasks_per_hour": 50.0,
    "total_cost_usd": 15.75,
    "active_workflows": 2
  },
  "agent_statuses": [
    {
      "agent_name": "research",
      "status": "active",
      "last_execution": "2026-03-02T10:30:00Z",
      "success_rate": 0.96,
      "avg_duration_seconds": 8.5,
      "total_executions": 450,
      "recent_errors": 2
    }
  ],
  "recent_errors": [
    {
      "error_type": "ValueError",
      "count": 12,
      "last_occurrence": "2026-03-02T11:15:00Z",
      "affected_agents": ["research", "docs"],
      "sample_message": "ValueError: Invalid input format"
    }
  ],
  "performance_trends": [
    {
      "timestamp": "2026-03-02T10:00:00Z",
      "metric_name": "task_completion_rate",
      "value": 48.0,
      "unit": "tasks/hour"
    }
  ],
  "active_alerts": [
    "⚠️ High error rate: 10.5%",
    "💰 High cost detected: $125.50"
  ]
}
```

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/dashboard?hours=48" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 2. Agent Status

**GET** `/api/v1/monitoring/agents/{agent_name}`

Get detailed status for a specific agent.

**Path Parameters:**
- `agent_name`: Agent type (`research`, `docs`, `sheets`, `slides`)

**Query Parameters:**
- `hours` (optional, default: 24): Time window

**Response:**
```json
{
  "agent_name": "research",
  "status": "active",
  "last_execution": "2026-03-02T11:20:00Z",
  "success_rate": 0.96,
  "avg_duration_seconds": 8.5,
  "total_executions": 450,
  "recent_errors": 2
}
```

**Status Values:**
- `active`: Agent is processing tasks
- `idle`: No recent activity (>1 hour)
- `error`: Recent failures detected

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/agents/research" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 3. System Metrics

**GET** `/api/v1/monitoring/metrics`

Get overall system performance metrics.

**Query Parameters:**
- `hours` (optional, default: 24): Time window

**Response:**
```json
{
  "total_tasks": 1250,
  "active_tasks": 5,
  "completed_tasks": 1200,
  "failed_tasks": 45,
  "avg_task_duration_seconds": 12.5,
  "tasks_per_hour": 50.0,
  "total_cost_usd": 15.75,
  "active_workflows": 2
}
```

---

### 4. Error Summary

**GET** `/api/v1/monitoring/errors`

Get recent errors grouped by type.

**Query Parameters:**
- `hours` (optional, default: 24): Time window

**Response:**
```json
[
  {
    "error_type": "ValueError",
    "count": 12,
    "last_occurrence": "2026-03-02T11:15:00Z",
    "affected_agents": ["research", "docs"],
    "sample_message": "ValueError: Invalid input format"
  },
  {
    "error_type": "ConnectionError",
    "count": 3,
    "last_occurrence": "2026-03-02T10:45:00Z",
    "affected_agents": ["sheets"],
    "sample_message": "ConnectionError: Google API timeout"
  }
]
```

---

### 5. Performance Trends

**GET** `/api/v1/monitoring/trends`

Get time-series performance metrics for visualization.

**Query Parameters:**
- `hours` (optional, default: 24): Time window

**Response:**
```json
[
  {
    "timestamp": "2026-03-02T10:00:00Z",
    "metric_name": "task_completion_rate",
    "value": 48.0,
    "unit": "tasks/hour"
  },
  {
    "timestamp": "2026-03-02T10:00:00Z",
    "metric_name": "error_rate",
    "value": 0.05,
    "unit": "percentage"
  },
  {
    "timestamp": "2026-03-02T10:00:00Z",
    "metric_name": "avg_cost_per_task",
    "value": 0.013,
    "unit": "USD"
  }
]
```

**Available Metrics:**
- `task_completion_rate`: Tasks completed per hour
- `error_rate`: Percentage of failed tasks
- `avg_cost_per_task`: Average LLM cost per task in USD

---

### 6. Active Alerts

**GET** `/api/v1/monitoring/alerts`

Check for active system alerts.

**Query Parameters:**
- `hours` (optional, default: 24): Time window

**Response:**
```json
[
  "⚠️ High error rate: 10.5%",
  "⚠️ Agent research experiencing errors",
  "💰 High cost detected: $125.50",
  "🐌 Slow task execution: avg 320s"
]
```

**Alert Types:**
- **High Error Rate**: >10% of tasks failing
- **Agent Errors**: Specific agent experiencing failures
- **High Cost**: Total cost exceeds $100 threshold
- **Slow Performance**: Average task duration >5 minutes

---

### 7. Health Check

**GET** `/api/v1/monitoring/health`

System health check (no authentication required).

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-02T11:22:00Z",
  "database": "healthy",
  "monitoring_api": "operational"
}
```

**Status Values:**
- `healthy`: All systems operational
- `degraded`: Some issues detected

---

## Alert System

### Built-in Alert Rules

The monitoring system includes automated alert detection:

| Alert | Condition | Threshold |
|-------|-----------|-----------|
| High Error Rate | Failed tasks / Total tasks | >10% |
| Agent Failure | Agent status = "error" | Any recent failure |
| High Cost | Total cost in time window | >$100 |
| Slow Performance | Average task duration | >300 seconds |

### Alert Response Format

Alerts are returned as human-readable strings with emoji indicators:
- ⚠️ Warning: Performance or error issues
- 💰 Cost: Budget concerns
- 🐌 Performance: Slow execution

---

## Integration with Existing Systems

### Budget Tracking

Monitoring integrates with the existing budget tracking system:
- Aggregates total LLM costs across time windows
- Includes cost-per-task metrics
- Triggers alerts on high spending

**Related**: See `docs/BUDGET_TRACKING.md`

### Workflow Execution

Tracks active multi-agent workflows:
- Counts workflows in "pending" or "running" status
- Enables workflow-specific monitoring

**Related**: See `docs/MULTI_AGENT_WORKFLOWS.md`

---

## Usage Examples

### Basic Monitoring Check

```python
import requests

headers = {"Authorization": f"Bearer {token}"}
response = requests.get(
    "http://localhost:8000/api/v1/monitoring/dashboard",
    headers=headers
)

dashboard = response.json()
print(f"Active tasks: {dashboard['system_metrics']['active_tasks']}")
print(f"Alerts: {dashboard['active_alerts']}")
```

### Check Specific Agent

```python
response = requests.get(
    "http://localhost:8000/api/v1/monitoring/agents/research",
    headers=headers,
    params={"hours": 48}
)

agent = response.json()
print(f"Agent: {agent['agent_name']}")
print(f"Status: {agent['status']}")
print(f"Success rate: {agent['success_rate']:.1%}")
```

### Error Analysis

```python
response = requests.get(
    "http://localhost:8000/api/v1/monitoring/errors",
    headers=headers
)

errors = response.json()
for error in errors[:5]:  # Top 5 errors
    print(f"{error['error_type']}: {error['count']} occurrences")
    print(f"  Affected: {', '.join(error['affected_agents'])}")
```

---

## Frontend Integration

### Dashboard Component

```javascript
// Fetch monitoring data
const response = await fetch('/api/v1/monitoring/dashboard?hours=24', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const data = await response.json();

// Display system metrics
console.log('System Health:', data.system_metrics);
console.log('Agent Statuses:', data.agent_statuses);
console.log('Active Alerts:', data.active_alerts);
```

### Real-time Updates

```javascript
// Poll monitoring endpoint every 30 seconds
setInterval(async () => {
  const response = await fetch('/api/v1/monitoring/dashboard', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const data = await response.json();
  
  updateDashboard(data);
  checkAlerts(data.active_alerts);
}, 30000);
```

### Chart Visualization

```javascript
// Fetch trends for charting
const response = await fetch('/api/v1/monitoring/trends?hours=168', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const trends = await response.json();

// Group by metric type
const completionRates = trends.filter(
  t => t.metric_name === 'task_completion_rate'
);

// Render chart (using Chart.js, Recharts, etc.)
renderTimeSeriesChart(completionRates);
```

---

## Performance Considerations

### Caching Strategy

- Dashboard data is computed on-demand (no caching currently)
- Consider Redis caching for high-traffic deployments
- Recommended cache TTL: 30-60 seconds

### Query Optimization

- All metrics use database indexes on `created_at` and `status`
- Large time windows (>7 days) may be slow with many tasks
- Consider database query optimization for production scale

### Rate Limiting

- Monitoring endpoints respect global rate limits
- Recommended polling interval: 30-60 seconds
- Use WebSocket subscriptions for real-time updates (future enhancement)

---

## Testing

Comprehensive test suite: `tests/monitoring/test_monitoring.py`

**Test Coverage:**
- ✅ Dashboard data completeness
- ✅ Agent status calculations
- ✅ Error grouping and summaries
- ✅ Performance trend generation
- ✅ Alert trigger conditions
- ✅ Authentication requirements
- ✅ Invalid input handling

**Run tests:**
```bash
pytest tests/monitoring/ -v
```

---

## Future Enhancements

### Planned Features

- [ ] **Custom Alert Rules**: User-defined alert conditions
- [ ] **WebSocket Subscriptions**: Real-time push notifications
- [ ] **Historical Data Export**: CSV/JSON download of metrics
- [ ] **Anomaly Detection**: ML-based anomaly identification
- [ ] **Per-User Metrics**: User-specific dashboards
- [ ] **Integration with External Tools**: DataDog, New Relic, Grafana

### Configuration Options

Future config options (not yet implemented):

```python
MONITORING_CONFIG = {
    "alert_thresholds": {
        "error_rate": 0.10,  # 10%
        "high_cost": 100.0,   # USD
        "slow_task": 300      # seconds
    },
    "cache_ttl": 60,          # seconds
    "max_trends_hours": 168   # 7 days
}
```

---

## Troubleshooting

### Common Issues

**Problem**: Dashboard returns empty data  
**Solution**: Ensure tasks have been created in the specified time window

**Problem**: Slow dashboard response  
**Solution**: Reduce time window or implement caching

**Problem**: Missing agent in agent_statuses  
**Solution**: Agent types are hardcoded; add new agents to the list in `monitoring.py`

**Problem**: Cost metrics are zero  
**Solution**: Ensure budget tracking is enabled and tasks are using tracked models

---

## Related Documentation

- **Budget Tracking**: `docs/BUDGET_TRACKING.md`
- **Multi-Agent Workflows**: `docs/MULTI_AGENT_WORKFLOWS.md`
- **API Rate Limiting**: `docs/API_RATE_LIMITING.md`
- **Performance Optimization**: `docs/PERFORMANCE_OPTIMIZATION.md`

---

## API Reference

**Base URL**: `/api/v1/monitoring`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/dashboard` | GET | ✅ | Complete monitoring dashboard |
| `/agents/{name}` | GET | ✅ | Specific agent status |
| `/metrics` | GET | ✅ | System-wide metrics |
| `/errors` | GET | ✅ | Error summary |
| `/trends` | GET | ✅ | Performance trends |
| `/alerts` | GET | ✅ | Active alerts |
| `/health` | GET | ❌ | Health check (public) |

---

**Completion Date**: 2026-03-02  
**Sprint**: 11  
**Status**: ✅ Production Ready
