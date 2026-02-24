# AgentHQ API Documentation

> **Version**: 1.0.0  
> **Base URL**: `https://api.agenthq.example.com/api/v1`  
> **Interactive Docs**: `/docs` (Swagger UI)  
> **Alternative Docs**: `/redoc` (ReDoc)

## Overview

AgentHQ is a Google Workspace AI automation platform that provides RESTful APIs for:

- 🤖 **Multi-Agent Task Execution** - Specialized agents for Docs, Sheets, and Slides
- 🔗 **Orchestration** - Coordinate multiple agents for complex workflows
- 💾 **Memory System** - Conversation history with semantic search
- 🔔 **Webhooks** - Google Drive change detection and triggers
- 📊 **Analytics** - Usage tracking and performance metrics

## Authentication

### OAuth 2.0 Flow

AgentHQ uses Google OAuth 2.0 for authentication. All API endpoints (except `/health` and `/docs`) require JWT authentication.

#### Step 1: Get Authorization URL

```bash
GET /api/v1/auth/google
```

**Response**:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

#### Step 2: User Authorizes

Redirect user to `auth_url`. After authorization, Google redirects to your callback URL with `code` parameter.

#### Step 3: Exchange Code for Token

```bash
POST /api/v1/auth/callback
Content-Type: application/json

{
  "code": "4/0AeaY...",
  "state": "csrf-token-here"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "1//0gKp...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### Step 4: Use Token in Requests

Include the token in all subsequent requests:

```bash
Authorization: Bearer eyJhbGci...
```

### Mobile/Guest Authentication

For mobile apps or guest access:

```bash
POST /api/v1/auth/mobile
Content-Type: application/json

{
  "id_token": "google-id-token-here"
}
```

## Core API Endpoints

### Tasks

#### Create Task

```bash
POST /api/v1/tasks
Authorization: Bearer <token>
Content-Type: application/json

{
  "task_type": "docs",
  "prompt": "Create a product roadmap document for Q2 2026",
  "metadata": {
    "title": "Q2 2026 Product Roadmap"
  }
}
```

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": "docs",
  "status": "pending",
  "prompt": "Create a product roadmap document for Q2 2026",
  "created_at": "2026-02-24T17:30:00Z",
  "result": null
}
```

#### Get Task Status

```bash
GET /api/v1/tasks/{task_id}
Authorization: Bearer <token>
```

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": "docs",
  "status": "completed",
  "prompt": "Create a product roadmap document for Q2 2026",
  "created_at": "2026-02-24T17:30:00Z",
  "completed_at": "2026-02-24T17:32:15Z",
  "result": {
    "document_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "document_url": "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
    "title": "Q2 2026 Product Roadmap"
  }
}
```

**Task Statuses**:
- `pending` - Task created, waiting to start
- `running` - Task is being processed
- `completed` - Task finished successfully
- `failed` - Task failed (check `error` field)

#### List My Tasks

```bash
GET /api/v1/tasks?limit=20&offset=0
Authorization: Bearer <token>
```

**Query Parameters**:
- `limit` (optional, default: 20) - Number of tasks to return
- `offset` (optional, default: 0) - Pagination offset
- `status` (optional) - Filter by status: `pending`, `running`, `completed`, `failed`
- `task_type` (optional) - Filter by type: `docs`, `sheets`, `slides`, `orchestrator`

#### Retry Failed Task

```bash
POST /api/v1/tasks/{task_id}/retry
Authorization: Bearer <token>
```

#### Cancel Running Task

```bash
POST /api/v1/tasks/{task_id}/cancel
Authorization: Bearer <token>
```

### Orchestrator

Coordinate multiple agents for complex workflows.

#### Execute Complex Task

```bash
POST /api/v1/orchestrator/complex-task
Authorization: Bearer <token>
Content-Type: application/json

{
  "description": "Research AI trends, create a summary document, and generate a presentation with charts",
  "context": {
    "target_audience": "executive team",
    "deadline": "2026-03-01"
  }
}
```

**Response**:
```json
{
  "orchestration_id": "orch-550e8400",
  "status": "running",
  "agents": [
    {
      "agent_type": "research",
      "status": "completed"
    },
    {
      "agent_type": "docs",
      "status": "running"
    },
    {
      "agent_type": "slides",
      "status": "pending"
    }
  ]
}
```

#### Plan Complex Task

Get an execution plan without running it:

```bash
POST /api/v1/orchestrator/plan
Authorization: Bearer <token>
Content-Type: application/json

{
  "description": "Analyze Q4 sales data and create a report"
}
```

### Memory

#### Search Memories

```bash
GET /api/v1/memory/search?query=product+roadmap&limit=10
Authorization: Bearer <token>
```

**Response**:
```json
{
  "results": [
    {
      "id": "mem-123",
      "content": "User requested Q2 2026 product roadmap focusing on AI features",
      "timestamp": "2026-02-24T17:30:00Z",
      "similarity": 0.92,
      "metadata": {
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "task_type": "docs"
      }
    }
  ]
}
```

#### Get Memory Timeline

```bash
GET /api/v1/memory/timeline?limit=50&offset=0
Authorization: Bearer <token>
```

#### Add Manual Memory

```bash
POST /api/v1/memory
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "User prefers concise summaries over detailed reports",
  "metadata": {
    "source": "manual",
    "category": "preference"
  }
}
```

### Webhooks

#### Subscribe to Google Drive Changes

```bash
POST /api/v1/webhooks/drive/watch
Authorization: Bearer <token>
Content-Type: application/json

{
  "file_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "webhook_url": "https://your-app.com/webhook/drive"
}
```

When the file changes, AgentHQ will POST to your webhook URL:

```json
{
  "event": "file.updated",
  "file_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "timestamp": "2026-02-24T17:30:00Z",
  "changes": ["content"]
}
```

### Analytics

#### Get Usage Statistics

```bash
GET /api/v1/analytics/usage?start_date=2026-02-01&end_date=2026-02-28
Authorization: Bearer <token>
```

**Response**:
```json
{
  "total_tasks": 142,
  "tasks_by_type": {
    "docs": 65,
    "sheets": 42,
    "slides": 35
  },
  "success_rate": 0.96,
  "avg_completion_time_seconds": 45.2
}
```

## Rate Limiting

**Default Limit**: 60 requests per minute per IP address.

When rate limit is exceeded, API returns:

```json
{
  "detail": "Rate limit exceeded. Try again in 30 seconds.",
  "retry_after": 30
}
```

**Headers**:
- `X-RateLimit-Limit: 60` - Maximum requests per minute
- `X-RateLimit-Remaining: 42` - Remaining requests
- `X-RateLimit-Reset: 1708796400` - Unix timestamp when limit resets

## Pagination

List endpoints support pagination via query parameters:

- `limit` (default: 20, max: 100) - Number of items per page
- `offset` (default: 0) - Number of items to skip

**Example**:
```bash
GET /api/v1/tasks?limit=50&offset=100
```

**Response includes pagination metadata**:
```json
{
  "items": [...],
  "total": 250,
  "limit": 50,
  "offset": 100
}
```

## Error Handling

### Error Response Format

```json
{
  "detail": "Human-readable error message",
  "error_code": "TASK_NOT_FOUND",
  "request_id": "req-550e8400"
}
```

### HTTP Status Codes

- `200 OK` - Success
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Authenticated but not authorized
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Service temporarily unavailable

## WebSocket API

Real-time task updates via WebSocket:

```javascript
const ws = new WebSocket('wss://api.agenthq.example.com/ws');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'auth',
    token: 'your-jwt-token'
  }));
  
  ws.send(JSON.stringify({
    type: 'subscribe',
    task_id: '550e8400-e29b-41d4-a716-446655440000'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Task update:', data);
  // { type: 'task.status', task_id: '...', status: 'completed', ... }
};
```

## SDKs and Client Libraries

### Python

```bash
pip install agenthq-client
```

```python
from agenthq import Client

client = Client(api_key='your-jwt-token')

# Create task
task = client.tasks.create(
    task_type='docs',
    prompt='Create a product roadmap',
    metadata={'title': 'Q2 Roadmap'}
)

# Wait for completion
result = task.wait()
print(f"Document URL: {result['document_url']}")
```

### JavaScript/TypeScript

```bash
npm install @agenthq/client
```

```typescript
import { AgentHQClient } from '@agenthq/client';

const client = new AgentHQClient({
  apiKey: 'your-jwt-token'
});

// Create task
const task = await client.tasks.create({
  taskType: 'docs',
  prompt: 'Create a product roadmap',
  metadata: { title: 'Q2 Roadmap' }
});

// Get result
const result = await client.tasks.get(task.id);
console.log(`Document URL: ${result.documentUrl}`);
```

## Examples

### Example 1: Automated Report Generation

Create a weekly sales report automatically:

```bash
POST /api/v1/orchestrator/complex-task
{
  "description": "Pull last week's sales data from Sheets, analyze trends, and create a summary document with charts",
  "context": {
    "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "date_range": "last_week"
  }
}
```

### Example 2: Dynamic Presentation Creation

Generate a presentation from research:

```bash
POST /api/v1/orchestrator/complex-task
{
  "description": "Research latest AI trends, summarize in 5 slides with visuals",
  "context": {
    "topic": "Generative AI in Healthcare",
    "slide_count": 5
  }
}
```

### Example 3: Webhook Automation

Auto-summarize new documents:

```bash
# 1. Subscribe to document changes
POST /api/v1/webhooks/drive/watch
{
  "folder_id": "folder-123",
  "webhook_url": "https://your-app.com/webhook"
}

# 2. When webhook fires, create summary task
POST /api/v1/tasks
{
  "task_type": "docs",
  "prompt": "Summarize this document in 3 bullet points",
  "metadata": {
    "source_document_id": "doc-456"
  }
}
```

## Best Practices

### 1. Use Task Preview Before Execution

Test your prompts with preview endpoint:

```bash
POST /api/v1/tasks/preview
{
  "task_type": "docs",
  "prompt": "Create Q2 roadmap"
}
```

### 2. Implement Retry Logic

Network errors can happen. Implement exponential backoff:

```python
import time

def create_task_with_retry(client, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.tasks.create(...)
        except NetworkError:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
```

### 3. Store Task IDs

Always store task IDs for later reference and tracking.

### 4. Monitor Rate Limits

Check `X-RateLimit-Remaining` header and implement backoff when low.

### 5. Use WebSockets for Real-Time Updates

For long-running tasks, use WebSocket subscriptions instead of polling.

## Support

- **Documentation**: https://github.com/choibongseok/my-superagent
- **Issues**: https://github.com/choibongseok/my-superagent/issues
- **Interactive API Docs**: `/docs` (when DEBUG=true)

## Changelog

### v1.0.0 (2026-02-24)

- ✅ Initial release
- ✅ Google OAuth 2.0 authentication
- ✅ Docs, Sheets, Slides agents
- ✅ Multi-agent orchestration
- ✅ Memory system with semantic search
- ✅ Google Drive webhooks
- ✅ Analytics endpoints
