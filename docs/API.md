# 🔌 AgentHQ API Documentation

> **Version**: 1.0  
> **Last Updated**: 2026-03-01  
> **Base URL**: `http://localhost:8000/api/v1`

---

## 📑 Table of Contents

1. [Authentication](#authentication)
2. [Agents API](#agents-api)
3. [Tasks API](#tasks-api)
4. [Budget API](#budget-api)
5. [OAuth API](#oauth-api)
6. [Sheets API](#sheets-api)
7. [Docs API](#docs-api)
8. [Fact Checking API](#fact-checking-api)
9. [Error Responses](#error-responses)

---

## 🔐 Authentication

All API endpoints require authentication via JWT token in the Authorization header:

```bash
Authorization: Bearer <your-jwt-token>
```

### Login

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

---

## 🤖 Agents API

### List Agents

```http
GET /agents
Authorization: Bearer <token>
```

**Query Parameters:**
- `type` (optional): Filter by agent type (`research`, `docs`, `sheets`, `slides`)
- `active` (optional): Filter by active status (`true`, `false`)

**Response:**
```json
{
  "agents": [
    {
      "id": 1,
      "name": "Research Assistant",
      "type": "research",
      "model": "gpt-4",
      "active": true,
      "created_at": "2026-03-01T00:00:00Z"
    }
  ]
}
```

### Create Agent

```http
POST /agents
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My Research Agent",
  "type": "research",
  "model": "gpt-4",
  "system_prompt": "You are a helpful research assistant...",
  "config": {
    "max_tokens": 4096,
    "temperature": 0.7
  }
}
```

**Supported Models:**
- OpenAI: `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
- Anthropic: `claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`

**Response:**
```json
{
  "id": 2,
  "name": "My Research Agent",
  "type": "research",
  "model": "gpt-4",
  "active": true,
  "created_at": "2026-03-01T05:00:00Z"
}
```

### Update Agent

```http
PATCH /agents/{agent_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Agent Name",
  "model": "claude-sonnet-4",
  "active": false
}
```

### Delete Agent

```http
DELETE /agents/{agent_id}
Authorization: Bearer <token>
```

---

## 📝 Tasks API

### Create Task

```http
POST /tasks
Authorization: Bearer <token>
Content-Type: application/json

{
  "agent_id": 1,
  "type": "research",
  "input": "Research the impact of AI on healthcare",
  "priority": "high",
  "deadline": "2026-03-05T00:00:00Z"
}
```

**Response:**
```json
{
  "task_id": "task_abc123",
  "status": "pending",
  "created_at": "2026-03-01T05:00:00Z"
}
```

### Get Task Status

```http
GET /tasks/{task_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "task_id": "task_abc123",
  "status": "completed",
  "progress": 100,
  "result": {
    "summary": "AI is transforming healthcare through...",
    "sources": ["https://..."]
  },
  "cost": {
    "input_tokens": 1500,
    "output_tokens": 800,
    "total_cost": 0.0045
  },
  "completed_at": "2026-03-01T05:15:00Z"
}
```

**Task Statuses:**
- `pending`: Task queued
- `processing`: Task in progress
- `completed`: Task finished successfully
- `failed`: Task failed
- `cancelled`: Task cancelled by user

### List Tasks

```http
GET /tasks
Authorization: Bearer <token>
```

**Query Parameters:**
- `status` (optional): Filter by status
- `agent_id` (optional): Filter by agent
- `limit` (default: 50): Number of results
- `offset` (default: 0): Pagination offset

---

## 💰 Budget API

### Get Budget Status

```http
GET /budget/status
Authorization: Bearer <token>
```

**Response:**
```json
{
  "user_id": 1,
  "monthly_limit": 50.00,
  "current_usage": 12.45,
  "percentage_used": 24.9,
  "alert_threshold": 80,
  "alerts_enabled": true,
  "current_period": {
    "start": "2026-03-01T00:00:00Z",
    "end": "2026-03-31T23:59:59Z"
  },
  "breakdown_by_model": {
    "gpt-4": 8.20,
    "claude-sonnet-4": 4.25
  }
}
```

### Update Budget Settings

```http
PATCH /budget/settings
Authorization: Bearer <token>
Content-Type: application/json

{
  "monthly_limit": 100.00,
  "alert_threshold": 75,
  "alerts_enabled": true
}
```

### Get Usage History

```http
GET /budget/usage
Authorization: Bearer <token>
```

**Query Parameters:**
- `start_date` (optional): Start date (ISO 8601)
- `end_date` (optional): End date (ISO 8601)
- `model` (optional): Filter by model

**Response:**
```json
{
  "total_cost": 12.45,
  "usage": [
    {
      "date": "2026-03-01",
      "model": "gpt-4",
      "input_tokens": 15000,
      "output_tokens": 8000,
      "cost": 0.45,
      "task_count": 12
    }
  ]
}
```

---

## 🔑 OAuth API

### List OAuth Providers

```http
GET /oauth/providers
Authorization: Bearer <token>
```

**Response:**
```json
{
  "providers": [
    {
      "name": "google",
      "display_name": "Google",
      "scopes": ["drive.file", "docs", "sheets"],
      "enabled": true
    },
    {
      "name": "github",
      "display_name": "GitHub",
      "scopes": ["repo", "user"],
      "enabled": true
    },
    {
      "name": "microsoft",
      "display_name": "Microsoft",
      "scopes": ["Files.ReadWrite", "User.Read"],
      "enabled": true
    }
  ]
}
```

### Initiate OAuth Flow

```http
GET /oauth/authorize/{provider}
Authorization: Bearer <token>
```

**Query Parameters:**
- `redirect_uri` (required): Callback URL
- `state` (optional): CSRF token

**Response:**
```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "random-csrf-token"
}
```

### OAuth Callback

```http
GET /oauth/callback/{provider}
```

**Query Parameters:**
- `code` (required): Authorization code
- `state` (required): CSRF token

**Response:**
```json
{
  "success": true,
  "provider": "google",
  "expires_at": "2026-03-08T05:00:00Z"
}
```

### List Connected Accounts

```http
GET /oauth/connections
Authorization: Bearer <token>
```

**Response:**
```json
{
  "connections": [
    {
      "provider": "google",
      "email": "user@gmail.com",
      "connected_at": "2026-03-01T00:00:00Z",
      "expires_at": "2026-03-08T05:00:00Z",
      "status": "active"
    }
  ]
}
```

### Revoke OAuth Connection

```http
DELETE /oauth/connections/{provider}
Authorization: Bearer <token>
```

---

## 📊 Sheets API

### Create Spreadsheet

```http
POST /sheets/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Sales Report Q1 2026",
  "sheets": [
    {
      "name": "Summary",
      "data": [
        ["Month", "Revenue", "Expenses"],
        ["January", 50000, 30000],
        ["February", 55000, 32000]
      ]
    }
  ]
}
```

**Response:**
```json
{
  "spreadsheet_id": "1abc123...",
  "url": "https://docs.google.com/spreadsheets/d/1abc123...",
  "title": "Sales Report Q1 2026"
}
```

### Add Formula

```http
POST /sheets/{spreadsheet_id}/formulas
Authorization: Bearer <token>
Content-Type: application/json

{
  "sheet_name": "Summary",
  "range": "D2",
  "formula": "=B2-C2"
}
```

### Apply Conditional Formatting

```http
POST /sheets/{spreadsheet_id}/conditional-formatting
Authorization: Bearer <token>
Content-Type: application/json

{
  "sheet_name": "Summary",
  "range": "B2:B10",
  "rule": {
    "type": "NUMBER_GREATER",
    "value": 50000,
    "format": {
      "backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}
    }
  }
}
```

### Create Pivot Table

```http
POST /sheets/{spreadsheet_id}/pivot-tables
Authorization: Bearer <token>
Content-Type: application/json

{
  "source_sheet": "Data",
  "source_range": "A1:D100",
  "target_sheet": "Pivot",
  "target_cell": "A1",
  "rows": ["Category"],
  "columns": ["Month"],
  "values": [{"field": "Revenue", "function": "SUM"}]
}
```

### Create Named Range

```http
POST /sheets/{spreadsheet_id}/named-ranges
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "SalesData",
  "range": "Summary!A1:D10"
}
```

### Add Data Validation

```http
POST /sheets/{spreadsheet_id}/data-validation
Authorization: Bearer <token>
Content-Type: application/json

{
  "sheet_name": "Summary",
  "range": "E2:E10",
  "validation": {
    "type": "ONE_OF_LIST",
    "values": ["Approved", "Pending", "Rejected"]
  }
}
```

---

## 📄 Docs API

### Create Document

```http
POST /docs/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Project Proposal",
  "content": "# Executive Summary\n\nThis proposal outlines..."
}
```

**Response:**
```json
{
  "document_id": "1xyz789...",
  "url": "https://docs.google.com/document/d/1xyz789...",
  "title": "Project Proposal"
}
```

### Update Document

```http
PATCH /docs/{document_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "operations": [
    {
      "type": "insert_text",
      "index": 1,
      "text": "Updated content..."
    },
    {
      "type": "apply_formatting",
      "range": {"start": 1, "end": 50},
      "style": {"bold": true, "fontSize": 14}
    }
  ]
}
```

---

## ✅ Fact Checking API

### Check Facts

```http
POST /fact-check
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "The Earth orbits the Sun once every 365.25 days.",
  "sources": ["wikipedia", "scientific_journals"]
}
```

**Response:**
```json
{
  "check_id": "fc_abc123",
  "status": "completed",
  "result": {
    "verdict": "accurate",
    "confidence": 0.95,
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Earth",
        "title": "Earth - Wikipedia",
        "relevant_excerpt": "Earth orbits the Sun once every 365.256 days..."
      }
    ],
    "explanation": "This statement is accurate. Earth's orbital period is approximately 365.25 days."
  }
}
```

**Verdicts:**
- `accurate`: Statement is factually correct
- `inaccurate`: Statement is factually incorrect
- `partially_accurate`: Statement is partially correct
- `unverifiable`: Cannot be verified with available sources

---

## ❌ Error Responses

All error responses follow this format:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Missing required field: agent_id",
    "details": {
      "field": "agent_id",
      "reason": "This field is required"
    }
  }
}
```

**Common Error Codes:**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Invalid or missing authentication token |
| `FORBIDDEN` | 403 | User lacks permission for this resource |
| `NOT_FOUND` | 404 | Resource not found |
| `INVALID_REQUEST` | 400 | Malformed request or validation error |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `BUDGET_EXCEEDED` | 402 | Monthly budget limit reached |
| `OAUTH_ERROR` | 401 | OAuth token expired or invalid |
| `INTERNAL_ERROR` | 500 | Server error |

---

## 📊 Rate Limits

- **Standard tier**: 100 requests/minute
- **Pro tier**: 500 requests/minute
- **Enterprise tier**: Custom limits

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1709272800
```

---

## 🔧 SDK Examples

### Python

```python
import requests

API_BASE = "http://localhost:8000/api/v1"
TOKEN = "your-jwt-token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Create a task
response = requests.post(
    f"{API_BASE}/tasks",
    headers=headers,
    json={
        "agent_id": 1,
        "type": "research",
        "input": "Research AI in healthcare"
    }
)

task = response.json()
print(f"Task created: {task['task_id']}")
```

### JavaScript

```javascript
const API_BASE = "http://localhost:8000/api/v1";
const TOKEN = "your-jwt-token";

async function createTask() {
  const response = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${TOKEN}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      agent_id: 1,
      type: "research",
      input: "Research AI in healthcare"
    })
  });
  
  const task = await response.json();
  console.log(`Task created: ${task.task_id}`);
}
```

### cURL

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "type": "research",
    "input": "Research AI in healthcare"
  }'
```

---

## 📚 Additional Resources

- [Getting Started Guide](./GETTING_STARTED.md)
- [Claude Integration](./CLAUDE_INTEGRATION.md)
- [Enhanced OAuth](./ENHANCED_OAUTH.md)
- [Budget Tracking](./BUDGET_TRACKING.md)
- [Sheets Advanced Features](./SHEETS_ADVANCED_FEATURES.md)

---

**Need help?** Open an issue on GitHub or contact support@agenthq.dev
