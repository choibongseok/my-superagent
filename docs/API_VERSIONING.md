# 🔄 API Versioning Strategy

> **Created**: 2026-03-02  
> **Status**: Active  
> **Current Version**: v2  
> **Deprecated Version**: v1 (sunset: June 1, 2026)

---

## Overview

AgentHQ uses semantic API versioning to provide a stable, predictable interface while allowing for improvements and breaking changes. This document outlines our versioning strategy, deprecation policy, and migration guidance.

---

## Version Negotiation

The API supports multiple version selection methods, applied in this priority order:

### 1. `X-API-Version` Header (Recommended)

```bash
curl -H "X-API-Version: v2" https://api.agenthq.io/api/v2/tasks
```

### 2. Accept Header with Custom Media Type

```bash
curl -H "Accept: application/vnd.agenthq.v2+json" https://api.agenthq.io/api/v2/tasks
```

### 3. URL Path

```bash
curl https://api.agenthq.io/api/v2/tasks
```

### 4. Default Fallback

If no version is specified, the API defaults to **v1** for backward compatibility.

---

## Current Versions

| Version | Status | Released | Deprecated | Sunset Date | Support Level |
|---------|--------|----------|------------|-------------|---------------|
| **v2** | ✅ Active | 2026-03-02 | - | - | Full support + new features |
| **v1** | ⚠️ Deprecated | 2025-09-01 | 2026-03-02 | 2026-06-01 | Security fixes only |

---

## Version Comparison

### v1 → v2 Key Changes

#### Tasks API

**v1 Response**:
```json
{
  "id": "uuid",
  "status": "completed",
  "prompt": "...",
  "result": "..."
}
```

**v2 Response** (Enhanced):
```json
{
  "id": "uuid",
  "status": "completed",
  "prompt": "...",
  "result": "...",
  "priority": 5,
  "tags": ["research", "urgent"],
  "estimated_duration_seconds": 120,
  "actual_duration_seconds": 105,
  "retry_count": 0,
  "celery_task_id": "celery-uuid"
}
```

#### Enhanced Features in v2

1. **Priority Support** (0-10)
   - Tasks can be prioritized in the queue
   - Higher priority tasks execute first
   
2. **Tags** (string[])
   - Organize tasks with custom tags
   - Filter and search by tags
   
3. **Duration Tracking**
   - Estimated vs actual duration
   - Performance analytics
   
4. **Better Pagination**
   - Metadata includes `total_pages`, `has_next`, `has_previous`
   - More filtering options (status, type, tags)
   - Flexible sorting
   
5. **Task Statistics** (NEW)
   - `GET /api/v2/tasks/stats` endpoint
   - Aggregate status counts
   - Average duration metrics
   
6. **Enhanced Error Messages**
   - Structured error responses
   - Error codes for programmatic handling
   - Detailed context

**v1 Error**:
```json
{
  "detail": "Task not found"
}
```

**v2 Error** (Improved):
```json
{
  "detail": {
    "error": "task_not_found",
    "message": "Task with ID abc123 not found",
    "task_id": "abc123"
  }
}
```

---

## Deprecation Policy

### Timeline

```
2026-03-02: v2 Released, v1 deprecated
     ↓
2026-04-01: v1 deprecation warnings in all responses
     ↓
2026-05-01: v1 rate limits reduced (50% of v2 limits)
     ↓
2026-06-01: v1 sunset (HTTP 410 Gone for all v1 endpoints)
```

### Deprecation Headers

All v1 responses include deprecation headers:

```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Sat, 1 Jun 2026 00:00:00 GMT
Link: </api/v2/docs>; rel="successor-version"
X-API-Version: v1
X-Supported-Versions: v1, v2
```

### Migration Window

**3 months** from deprecation announcement to sunset.

During this period:
- v1 remains fully functional
- Both v1 and v2 are documented
- Migration support available via support channels
- Automated migration tools provided

---

## Migration Guide

### Step 1: Update Client Headers

**Before** (v1 implicit):
```python
response = requests.get("https://api.agenthq.io/api/v1/tasks")
```

**After** (v2 explicit):
```python
headers = {"X-API-Version": "v2"}
response = requests.get("https://api.agenthq.io/api/v2/tasks", headers=headers)
```

### Step 2: Update Request Schemas

**v1 Task Creation**:
```python
task_data = {
    "prompt": "Research AI trends",
    "task_type": "research",
    "llm_provider": "openai",
    "llm_model": "gpt-4"
}
```

**v2 Task Creation** (Optional fields):
```python
task_data = {
    "prompt": "Research AI trends",
    "task_type": "research",
    "llm_provider": "openai",
    "llm_model": "gpt-4",
    "priority": 7,  # High priority
    "tags": ["research", "ai", "trends"],
    "estimated_duration_seconds": 180
}
```

### Step 3: Handle Enhanced Responses

**v1**:
```python
tasks = response.json()["tasks"]  # List[Task]
total = response.json()["total"]  # int
```

**v2**:
```python
data = response.json()
tasks = data["items"]  # List[TaskV2]
pagination = data["pagination"]  # { total, page, total_pages, has_next, ... }
```

### Step 4: Update Error Handling

**v1**:
```python
if response.status_code != 200:
    print(f"Error: {response.json()['detail']}")
```

**v2** (Structured errors):
```python
if response.status_code != 200:
    error = response.json()["detail"]
    print(f"Error [{error['error']}]: {error['message']}")
    # Handle specific error codes
    if error["error"] == "task_not_found":
        # ...
```

---

## Breaking Changes

### v1 → v2

1. **Pagination Response Structure**
   - v1: `{ tasks: [], total, page, page_size }`
   - v2: `{ items: [], pagination: { ... } }`
   
2. **Error Response Format**
   - v1: `{ detail: string }`
   - v2: `{ detail: { error, message, ... } }`
   
3. **Task Response Fields**
   - Added: `priority`, `tags`, `estimated_duration_seconds`, `actual_duration_seconds`, `retry_count`
   
4. **New Endpoints (v2 only)**
   - `GET /api/v2/tasks/stats` - Task statistics

### Backward Compatibility

v2 is **not** backward compatible with v1 clients that rely on:
- Specific response structures (pagination, errors)
- Field names (no renamed fields, only additions)

However, v1 endpoints remain functional until sunset.

---

## Best Practices

### For API Consumers

1. **Always specify API version** (via header or URL)
2. **Don't rely on default version** (may change)
3. **Monitor deprecation headers** (`Deprecation`, `Sunset`)
4. **Test against v2 early** (before v1 sunset)
5. **Use semantic versioning** in your client code

### For API Developers

1. **Never break v2 contracts** without incrementing to v3
2. **Additive changes only** within a major version
3. **Document all changes** in this file
4. **Provide migration tools** for breaking changes
5. **Minimum 3-month deprecation window**

---

## Version Support Policy

### Active Version (v2)

- ✅ All new features
- ✅ Performance improvements
- ✅ Bug fixes
- ✅ Security patches
- ✅ Full documentation
- ✅ Community support

### Deprecated Version (v1)

- ❌ No new features
- ❌ No performance improvements
- ⚠️ Critical bug fixes only
- ✅ Security patches
- ⚠️ Documentation maintained (migration guide)
- ⚠️ Limited support

### Sunset Version

- ❌ HTTP 410 Gone
- ❌ No support
- ⚠️ Migration guide available

---

## FAQ

### Q: Can I use v1 and v2 simultaneously?

**A:** Yes! Different clients can use different versions. Mix and match based on your migration timeline.

### Q: What happens if I don't migrate before sunset?

**A:** All v1 endpoints will return `HTTP 410 Gone` after June 1, 2026. Your requests will fail.

### Q: Will my API keys work with v2?

**A:** Yes! Authentication is version-agnostic. Same keys work for both v1 and v2.

### Q: Are there any rate limit differences?

**A:** Starting April 1, 2026, v1 rate limits will be reduced to 50% of v2 limits to encourage migration.

### Q: How do I test v2 before migrating?

**A:** Simply add `X-API-Version: v2` header to your requests. No other changes needed to start testing.

### Q: Can I request an extension for v1 sunset?

**A:** Enterprise customers can request up to 3 months extension. Contact support@agenthq.io.

---

## Future Versions

### v3 (Planned: Q4 2026)

Potential breaking changes under consideration:
- GraphQL endpoint
- Webhook-based task notifications
- Batch operations
- Streaming responses for long-running tasks

**Timeline**: Announcement at least 6 months before release.

---

## Support

- **Documentation**: https://docs.agenthq.io/api/versioning
- **Migration Help**: support@agenthq.io
- **Slack Community**: #api-versioning channel
- **GitHub Issues**: https://github.com/agenthq/backend/issues

---

**Last Updated**: 2026-03-02 by Sprint 13 Team 🚀
