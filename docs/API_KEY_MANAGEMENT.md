# 🔑 API Key Management

> **Sprint 14 Feature** (2026-03-02)  
> **Status**: ✅ Complete

## Overview

API Key Management provides secure programmatic access to AgentHQ API endpoints. Instead of using OAuth tokens, users can generate API keys with customizable scopes and expiration dates for automation, integrations, and third-party applications.

## Features

### Core Functionality

- **Per-User API Keys**: Each user can generate multiple API keys
- **Scoped Permissions**: Fine-grained access control (read, write, admin)
- **Key Rotation**: Generate new keys while invalidating old ones
- **Expiration**: Optional time-based key expiration
- **Usage Analytics**: Track requests per key with detailed stats
- **Key Management**: Create, list, update, deactivate, and delete keys

### Security Features

- **SHA-256 Hashing**: Keys are hashed before storage (never stored in plaintext)
- **Prefix Identification**: First 8 characters shown for identification (ahq_xxxxxxxx)
- **One-Time Display**: Actual key only shown during creation/rotation
- **Activity Tracking**: Last used timestamp and total usage count
- **Rate Limiting**: API keys subject to same rate limits as user accounts
- **Audit Trail**: Complete usage logs with endpoint, method, status, IP, and user agent

## Quick Start

### Creating an API Key

```bash
curl -X POST https://agenthq.example.com/api/v1/api-keys \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key",
    "scopes": ["read", "write"],
    "expires_in_days": 90
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Production API Key",
  "key_prefix": "ahq_abcd",
  "scopes": ["read", "write"],
  "expires_at": "2026-06-01T00:00:00Z",
  "last_used_at": null,
  "is_active": true,
  "usage_count": 0,
  "created_at": "2026-03-02T12:00:00Z",
  "api_key": "ahq_abcdefghijklmnopqrstuvwxyz1234567890ABCD"
}
```

**⚠️ Important**: Save the `api_key` value immediately - it will **never be shown again**!

### Using an API Key

Include the API key in the `X-API-Key` header:

```bash
curl -X GET https://agenthq.example.com/api/v1/tasks \
  -H "X-API-Key: ahq_abcdefghijklmnopqrstuvwxyz1234567890ABCD"
```

API keys work as a drop-in replacement for JWT Bearer tokens. All endpoints that accept `Authorization: Bearer <token>` also accept `X-API-Key: <key>`.

## API Endpoints

### Create API Key

**POST** `/api/v1/api-keys`

Create a new API key for the authenticated user.

**Request Body:**
```json
{
  "name": "string",              // Required: User-friendly name
  "scopes": ["read", "write"],   // Required: List of scopes
  "expires_in_days": 30          // Optional: Days until expiration (1-365)
}
```

**Valid Scopes:**
- `read`: Read access to user's resources
- `write`: Write access (create, update resources)
- `admin`: Full administrative access (admin users only)

**Response:** `201 Created` with API key details (including actual key)

---

### List API Keys

**GET** `/api/v1/api-keys`

List all API keys for the authenticated user.

**Query Parameters:**
- `include_inactive` (boolean, default: false): Include deactivated keys

**Response:** `200 OK` with array of API key objects (without actual keys)

---

### Get API Key

**GET** `/api/v1/api-keys/{key_id}`

Get details of a specific API key.

**Response:** `200 OK` with API key details (without actual key)

---

### Update API Key

**PATCH** `/api/v1/api-keys/{key_id}`

Update API key name, scopes, or activation status.

**Request Body:**
```json
{
  "name": "string",              // Optional: New name
  "scopes": ["read"],            // Optional: New scopes
  "is_active": false             // Optional: Deactivate key
}
```

**Response:** `200 OK` with updated API key details

---

### Delete API Key

**DELETE** `/api/v1/api-keys/{key_id}`

Permanently delete an API key (cannot be undone).

**Response:** `204 No Content`

---

### Rotate API Key

**POST** `/api/v1/api-keys/{key_id}/rotate`

Generate a new key while keeping the same configuration. The old key is immediately invalidated.

**Response:** `200 OK` with new API key (including actual key)

**⚠️ Important**: Save the new key immediately - it will never be shown again!

---

### Get API Key Statistics

**GET** `/api/v1/api-keys/{key_id}/stats`

Get usage statistics for an API key.

**Response:** `200 OK`
```json
{
  "total_requests": 1234,
  "requests_by_endpoint": {
    "/api/v1/tasks": 800,
    "/api/v1/chats": 400,
    "/api/v1/health": 34
  },
  "requests_by_status": {
    "200": 1200,
    "404": 30,
    "500": 4
  },
  "last_24h_requests": 45,
  "last_7d_requests": 320
}
```

## Authentication Flow

API Key authentication is an alternative to JWT Bearer tokens:

```
1. User requests API key via JWT-authenticated endpoint
2. Server generates secure random key (ahq_<random>)
3. Server hashes key with SHA-256 and stores hash
4. Server returns actual key to user (only once)
5. User includes key in X-API-Key header for subsequent requests
6. Server hashes incoming key and looks up in database
7. Server validates key (active, not expired, user active)
8. Server authenticates user and processes request
9. Server logs usage (endpoint, status, timestamp, etc.)
```

### Dual Authentication Support

The `/api/v1/*` endpoints support **both** authentication methods:

**JWT Bearer Token:**
```bash
curl -H "Authorization: Bearer <jwt_token>" \
  https://agenthq.example.com/api/v1/tasks
```

**API Key:**
```bash
curl -H "X-API-Key: <api_key>" \
  https://agenthq.example.com/api/v1/tasks
```

If both are provided, API key takes precedence.

## Scopes and Permissions

### Scope Hierarchy

1. **read**: Read-only access
   - GET endpoints
   - List resources
   - View analytics

2. **write**: Read + write access
   - All `read` permissions
   - POST, PATCH, DELETE endpoints
   - Create/update/delete resources

3. **admin**: Full administrative access
   - All `write` permissions
   - Admin endpoints (`/api/v1/admin/*`)
   - User management
   - System configuration

**Note**: Only users with `is_admin=true` can create API keys with the `admin` scope.

### Scope Validation

When creating or updating an API key:
- Non-admin users **cannot** set `admin` scope
- Invalid scopes are rejected with `400 Bad Request`
- Scopes are validated on every API request

### Checking Scopes Programmatically

For endpoints that require specific scopes, use the `require_api_key_scope` dependency:

```python
from app.middleware.api_key_auth import require_api_key_scope

@router.get(
    "/admin/stats",
    dependencies=[Depends(require_api_key_scope("admin"))]
)
async def get_admin_stats():
    # Only accessible with admin-scoped API key
    ...
```

## Usage Tracking

### Automatic Logging

Every API request authenticated via API key is automatically logged with:

- **Endpoint**: Full request path
- **Method**: HTTP method (GET, POST, etc.)
- **Status Code**: Response status code
- **IP Address**: Client IP address
- **User Agent**: Client user agent string
- **Timestamp**: Request time (UTC)

### Performance Considerations

- Usage logs are written **asynchronously** to avoid slowing down requests
- Logs are stored in the `api_key_usage` table
- Old logs can be archived/deleted via maintenance scripts
- Usage count and last_used_at are updated on the API key record

### Analytics Queries

Get detailed analytics via the stats endpoint:

```bash
curl -X GET \
  https://agenthq.example.com/api/v1/api-keys/{key_id}/stats \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Use this data for:
- Billing and cost attribution
- Rate limit optimization
- Security auditing
- Usage pattern analysis

## Security Best Practices

### Key Storage

- **Never commit API keys to Git** - use environment variables
- **Never log API keys** - they are credentials, not metadata
- **Use secrets management** - AWS Secrets Manager, HashiCorp Vault, etc.
- **Rotate keys regularly** - use `/api-keys/{id}/rotate` endpoint
- **Delete unused keys** - reduce attack surface

### Key Distribution

- **One key per application** - easier to track and revoke
- **Short expiration for testing** - use temporary keys for development
- **Separate keys for prod/staging** - isolate environments
- **Document key owners** - use descriptive names like "GitHub Actions CI"

### Monitoring and Alerts

- **Track failed authentication attempts** - monitor 401 responses
- **Alert on unusual patterns** - sudden spike in requests
- **Review usage logs regularly** - check `api_key_usage` table
- **Audit active keys periodically** - deactivate unused keys

### Incident Response

**If an API key is compromised:**

1. **Immediately deactivate** the key via PATCH endpoint:
   ```bash
   curl -X PATCH https://agenthq.example.com/api/v1/api-keys/{key_id} \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -d '{"is_active": false}'
   ```

2. **Review usage logs** to assess impact:
   ```bash
   curl -X GET https://agenthq.example.com/api/v1/api-keys/{key_id}/stats \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

3. **Create a new key** with different scopes if needed

4. **Notify security team** if malicious activity detected

## Database Schema

### `api_keys` Table

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    key_prefix VARCHAR(10) NOT NULL,
    scopes TEXT NOT NULL DEFAULT 'read',
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Indexes
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE UNIQUE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at);
CREATE INDEX idx_api_keys_user_active ON api_keys(user_id, is_active);
```

### `api_key_usage` Table

```sql
CREATE TABLE api_key_usage (
    id UUID PRIMARY KEY,
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(512),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Indexes
CREATE INDEX idx_usage_key_time ON api_key_usage(api_key_id, created_at);
CREATE INDEX idx_usage_endpoint_time ON api_key_usage(endpoint, created_at);
CREATE INDEX idx_usage_status_time ON api_key_usage(status_code, created_at);
```

## Migration

The API key tables are created by Alembic migration `010_api_key_management.py`.

**Run migration:**
```bash
cd backend
alembic upgrade head
```

**Rollback (if needed):**
```bash
alembic downgrade -1
```

## Testing

Run the comprehensive test suite:

```bash
cd backend
pytest tests/api/test_api_keys.py -v
```

**Test Coverage:**
- ✅ API key CRUD operations (create, list, get, update, delete)
- ✅ API key authentication (valid, invalid, expired, inactive)
- ✅ Usage tracking (count, last_used_at, stats)
- ✅ Scope validation (read, write, admin)
- ✅ Key rotation
- ✅ Admin-only features
- ✅ Multi-user isolation

**Total Tests**: 20+ scenarios

## Examples

### Python Client

```python
import httpx

API_KEY = "ahq_abcdefghijklmnopqrstuvwxyz1234567890ABCD"
BASE_URL = "https://agenthq.example.com/api/v1"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"X-API-Key": API_KEY}
)

# List tasks
response = client.get("/tasks")
tasks = response.json()

# Create task
response = client.post("/tasks", json={
    "type": "research",
    "prompt": "Research quantum computing",
    "agent_config": {"model": "gpt-4"}
})
task = response.json()
```

### JavaScript/Node.js Client

```javascript
const axios = require('axios');

const client = axios.create({
  baseURL: 'https://agenthq.example.com/api/v1',
  headers: {
    'X-API-Key': 'ahq_abcdefghijklmnopqrstuvwxyz1234567890ABCD'
  }
});

// List tasks
const { data: tasks } = await client.get('/tasks');

// Create task
const { data: task } = await client.post('/tasks', {
  type: 'research',
  prompt: 'Research quantum computing',
  agent_config: { model: 'gpt-4' }
});
```

### CI/CD Pipeline (GitHub Actions)

```yaml
name: Run Agent Task

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM

jobs:
  weekly-report:
    runs-on: ubuntu-latest
    steps:
      - name: Generate Weekly Report
        run: |
          curl -X POST https://agenthq.example.com/api/v1/tasks \
            -H "X-API-Key: ${{ secrets.AGENTHQ_API_KEY }}" \
            -H "Content-Type: application/json" \
            -d '{
              "type": "docs",
              "prompt": "Generate weekly sales report for last 7 days",
              "agent_config": {
                "model": "gpt-4",
                "output_format": "google_docs"
              }
            }'
```

### Terraform (Infrastructure as Code)

```hcl
resource "agenthq_api_key" "ci_cd" {
  name             = "CI/CD Pipeline Key"
  scopes           = ["read", "write"]
  expires_in_days  = 90
}

output "api_key" {
  value     = agenthq_api_key.ci_cd.api_key
  sensitive = true
}
```

## Comparison: API Keys vs JWT Tokens

| Feature | JWT Tokens | API Keys |
|---------|-----------|----------|
| **Lifetime** | Short (15-60 min) | Long (days to never) |
| **Refresh** | Automatic (refresh token) | Manual rotation |
| **Revocation** | Only on expiry | Instant (deactivate) |
| **Use Case** | Interactive web/mobile | Automation, integrations |
| **Scopes** | User permissions | Configurable (read/write/admin) |
| **Audit** | Limited | Full usage logs |
| **Rotation** | Automatic | Manual |
| **Best For** | Human users | Machines, scripts, CI/CD |

## Future Enhancements

### Planned Features (Phase 3)

- [ ] **IP Whitelisting**: Restrict keys to specific IP ranges
- [ ] **Webhook Signing**: Sign outbound webhooks with key
- [ ] **Rate Limit Overrides**: Per-key rate limit configuration
- [ ] **Team API Keys**: Shared keys for organizations
- [ ] **Usage Quotas**: Hard limits on requests per key
- [ ] **Automatic Rotation**: Scheduled key rotation
- [ ] **Key Policies**: JSON-based fine-grained permissions

### Integration Ideas

- [ ] **Zapier/Make.com**: OAuth-less integration via API keys
- [ ] **GitHub Actions**: Marketplace action for AgentHQ
- [ ] **Postman Collection**: Pre-configured with API key auth
- [ ] **Terraform Provider**: Manage keys as infrastructure
- [ ] **CLI Tool**: `agenthq-cli` with key management

## Troubleshooting

### 401 Unauthorized

**Problem**: API key not accepted

**Solutions**:
1. Check key format (must start with `ahq_`)
2. Verify key is active: `GET /api-keys/{id}`
3. Check expiration: `expires_at` field
4. Ensure user account is active

### 403 Forbidden

**Problem**: API key lacks required scope

**Solutions**:
1. Check key scopes: `GET /api-keys/{id}`
2. Update scopes: `PATCH /api-keys/{id}` with new scopes
3. Create new key with appropriate scopes

### Usage Not Tracked

**Problem**: `usage_count` or `last_used_at` not updating

**Solutions**:
1. Check database logs for errors
2. Verify Redis connection (usage logging uses Redis)
3. Check `api_key_usage` table for recent entries
4. Restart backend workers: `docker restart agenthq-backend`

### Key Not Working After Rotation

**Problem**: Rotated key returns 401

**Solutions**:
1. Verify you're using the **new** key (from rotation response)
2. Check key was actually rotated: `GET /api-keys/{id}` (key_prefix changed)
3. Clear any cached keys in your application

## Support

For issues, questions, or feature requests:

- **Documentation**: https://docs.agenthq.example.com
- **GitHub Issues**: https://github.com/yourusername/agenthq/issues
- **Discord**: https://discord.gg/agenthq
- **Email**: support@agenthq.example.com

---

**Last Updated**: 2026-03-02 (Sprint 14)  
**Author**: AgentHQ Team  
**Version**: 1.0
