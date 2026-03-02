# 🗂️ Smart Workspace Manager

**Status**: ✅ Completed (Sprint 16)  
**Version**: 1.0.0  
**Last Updated**: 2026-03-02

---

## Overview

The Smart Workspace Manager provides intelligent analysis and organization of user's Google Drive workspace. It helps identify duplicate files, stale content, storage usage patterns, and provides automated cleanup and organization features.

## Features

### 1. Workspace Analysis

Comprehensive analysis of Drive files including:

- **Total file count and storage usage**
- **Duplicate file detection** (by name and size)
- **Stale file identification** (not accessed in 90+ days)
- **Storage breakdown by file type** (documents, spreadsheets, presentations, images, etc.)
- **Smart organization suggestions** (archive, organize by year, remove duplicates)

### 2. Automated Organization

Execute organization operations based on analysis suggestions:

- **Archive Old Files**: Move files not accessed in 180+ days to an "Archive" folder
- **Organize by Year**: Create year-based folder structure (e.g., Archive/2024, Archive/2023)
- **Remove Duplicates**: Delete duplicate files (keeps the newest version)

### 3. Cleanup Tracking

Audit trail of all workspace operations:

- Operation type and timestamp
- Number of files affected
- Storage space freed
- Detailed operation metadata

---

## API Endpoints

### Analyze Workspace

Start a comprehensive workspace analysis.

**Endpoint**: `POST /api/v1/workspace/analyze`

**Authentication**: Required (JWT or API key)

**Response**:
```json
{
  "id": 1,
  "user_id": 123,
  "analyzed_at": "2026-03-02T16:00:00Z",
  "total_files": 157,
  "total_size_bytes": 104857600,
  "duplicate_files": [
    {
      "files": [
        {
          "id": "abc123",
          "name": "report.pdf",
          "size": 1048576,
          "modified": "2024-02-01T10:00:00Z",
          "link": "https://drive.google.com/file/d/abc123"
        },
        {
          "id": "def456",
          "name": "report.pdf",
          "size": 1048576,
          "modified": "2024-01-15T10:00:00Z",
          "link": "https://drive.google.com/file/d/def456"
        }
      ],
      "total_size": 2097152
    }
  ],
  "stale_files": [
    {
      "id": "xyz789",
      "name": "old_presentation.pptx",
      "size": 5242880,
      "last_accessed": "2023-06-01T00:00:00Z",
      "days_stale": 275,
      "link": "https://docs.google.com/presentation/d/xyz789"
    }
  ],
  "storage_breakdown": {
    "categories": [
      {"type": "documents", "count": 45, "size": 25165824},
      {"type": "spreadsheets", "count": 32, "size": 18874368},
      {"type": "presentations", "count": 18, "size": 41943040},
      {"type": "images", "count": 52, "size": 15728640},
      {"type": "pdfs", "count": 10, "size": 3145728}
    ]
  },
  "organization_suggestions": [
    {
      "type": "archive_old_files",
      "priority": "high",
      "description": "Archive 12 files older than 6 months",
      "action": "move_to_archive",
      "file_count": 12,
      "space_saved_bytes": 15728640
    },
    {
      "type": "remove_duplicates",
      "priority": "medium",
      "description": "Remove 8 duplicate files",
      "action": "delete_duplicates",
      "file_count": 8,
      "space_saved_bytes": 10485760
    }
  ]
}
```

---

### Get Recent Insights

Retrieve recent workspace analysis results.

**Endpoint**: `GET /api/v1/workspace/insights?limit=10`

**Authentication**: Required

**Query Parameters**:
- `limit` (optional): Number of results (default: 10)

**Response**: Array of workspace insights (same format as analyze response)

---

### Get Specific Insight

Retrieve a specific workspace insight by ID.

**Endpoint**: `GET /api/v1/workspace/insights/{insight_id}`

**Authentication**: Required

**Response**: Single workspace insight object

---

### Execute Organization

Execute an organization operation based on a suggestion.

**Endpoint**: `POST /api/v1/workspace/organize`

**Authentication**: Required

**Request Body**:
```json
{
  "insight_id": 1,
  "suggestion_type": "archive_old_files"
}
```

**Supported Operations**:
- `archive_old_files` - Move stale files to Archive folder
- `organize_by_year` - Create year-based folder structure
- `remove_duplicates` - Delete duplicate files (keep newest)

**Response**:
```json
{
  "id": 10,
  "user_id": 123,
  "insight_id": 1,
  "operation_type": "archive_old_files",
  "performed_at": "2026-03-02T16:30:00Z",
  "files_affected": 12,
  "bytes_freed": 15728640,
  "details": {
    "archive_folder_id": "folder_abc123"
  },
  "error_message": null
}
```

---

### Get Cleanup Logs

Retrieve workspace cleanup operation history.

**Endpoint**: `GET /api/v1/workspace/cleanup-logs?limit=20`

**Authentication**: Required

**Query Parameters**:
- `limit` (optional): Number of results (default: 20)

**Response**: Array of cleanup log objects

---

## Database Schema

### workspace_insights

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Foreign key to users table |
| analyzed_at | DateTime | Timestamp of analysis |
| total_files | Integer | Total file count |
| total_size_bytes | Integer | Total storage in bytes |
| duplicate_files | JSON | List of duplicate file groups |
| stale_files | JSON | List of stale files |
| storage_breakdown | JSON | Storage by file type |
| organization_suggestions | JSON | Auto-org recommendations |

### workspace_cleanup_logs

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | Foreign key to users table |
| insight_id | Integer | Foreign key to insights (nullable) |
| operation_type | String(50) | Type of operation |
| performed_at | DateTime | Timestamp of operation |
| files_affected | Integer | Number of files modified |
| bytes_freed | Integer | Storage space freed |
| details | JSON | Operation metadata |
| error_message | Text | Error details (if failed) |

---

## Implementation Details

### Duplicate Detection

Files are considered duplicates if they have:
1. Identical filenames
2. Identical file sizes

The system groups duplicates and keeps the newest version based on `modifiedTime`.

### Stale File Detection

Files are considered stale if they haven't been accessed (viewed or modified) in 90+ days. The system checks:
1. `viewedByMeTime` (preferred)
2. Falls back to `modifiedTime` if view time unavailable

### Storage Categorization

Files are grouped by MIME type into categories:
- **documents**: Google Docs, Word files
- **spreadsheets**: Google Sheets, Excel files
- **presentations**: Google Slides, PowerPoint files
- **images**: JPEG, PNG, GIF, etc.
- **videos**: MP4, AVI, MOV, etc.
- **pdfs**: PDF documents
- **folders**: Google Drive folders
- **other**: Everything else

### Organization Suggestions

The system generates suggestions based on:
- **Archive priority**: HIGH if 10+ stale files found
- **Duplicate priority**: MEDIUM if 5+ duplicate groups found
- **Organize by year**: MEDIUM if 10+ files without year-based folders

---

## Performance Considerations

### Analysis Performance

- **Pagination**: Fetches files in batches of 100
- **Timeout**: Default 60-second timeout for Drive API calls
- **Rate limiting**: Respects Google Drive API quotas
- **Caching**: Insights are cached in database for reuse

### Cleanup Performance

- **Batch limits**: Max 50 files per operation to prevent timeouts
- **Atomic operations**: Each file operation is independent
- **Error handling**: Continues on single file failure, logs errors

---

## Security & Privacy

### Data Access

- Users can only access their own workspace insights
- Drive API scopes required: `drive.readonly` (analysis), `drive.file` (cleanup)
- OAuth tokens are encrypted at rest

### Cleanup Safety

- **No permanent deletion**: Duplicates are deleted, but can be recovered from Drive Trash (30 days)
- **Archive preservation**: Old files are moved, not deleted
- **Audit trail**: All operations are logged with user_id and timestamp

---

## Error Handling

### Common Errors

| Error | Status Code | Description |
|-------|-------------|-------------|
| Drive API unavailable | 500 | Google Drive service error |
| Invalid insight ID | 404 | Insight not found or not owned by user |
| Insufficient permissions | 403 | Missing Drive API scopes |
| Invalid suggestion type | 400 | Unknown organization operation |

### Error Response Format

```json
{
  "detail": "Workspace analysis failed: Drive API quota exceeded"
}
```

---

## Usage Examples

### Python Example

```python
import requests

# Step 1: Analyze workspace
response = requests.post(
    "https://api.agenthq.com/api/v1/workspace/analyze",
    headers={"Authorization": f"Bearer {access_token}"}
)
insight = response.json()

print(f"Total files: {insight['total_files']}")
print(f"Duplicates: {len(insight['duplicate_files'])} groups")

# Step 2: Execute cleanup
if insight['organization_suggestions']:
    suggestion = insight['organization_suggestions'][0]
    
    response = requests.post(
        "https://api.agenthq.com/api/v1/workspace/organize",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "insight_id": insight['id'],
            "suggestion_type": suggestion['type']
        }
    )
    
    result = response.json()
    print(f"Cleaned up {result['files_affected']} files")
    print(f"Freed {result['bytes_freed']} bytes")
```

### cURL Example

```bash
# Analyze workspace
curl -X POST https://api.agenthq.com/api/v1/workspace/analyze \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get insights
curl https://api.agenthq.com/api/v1/workspace/insights?limit=5 \
  -H "Authorization: Bearer YOUR_TOKEN"

# Execute cleanup
curl -X POST https://api.agenthq.com/api/v1/workspace/organize \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "insight_id": 1,
    "suggestion_type": "archive_old_files"
  }'

# Check cleanup history
curl https://api.agenthq.com/api/v1/workspace/cleanup-logs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Future Enhancements

### Planned Features (Sprint 17+)

- **Smart tagging**: Auto-tag files by content (e.g., "contracts", "invoices")
- **Workspace health score**: 0-100 score based on organization level
- **Custom organization rules**: User-defined folder structures
- **Scheduled cleanups**: Automatic monthly/quarterly cleanup jobs
- **Team workspace analytics**: Aggregate insights for shared drives

### Advanced Features

- **AI-powered categorization**: Use LLM to suggest better file names/folders
- **Similarity detection**: Detect similar content (not just exact duplicates)
- **Version history cleanup**: Remove old document versions
- **Access pattern analysis**: Recommend which files to archive based on collaboration patterns

---

## Testing

### Test Coverage

- **Unit tests**: 15+ test scenarios for analyzer service
- **Integration tests**: 8+ test scenarios for API endpoints
- **Cleanup operation tests**: 3+ test scenarios for each operation type
- **Target coverage**: 85%+

### Running Tests

```bash
# Run all workspace tests
pytest tests/api/test_workspace_analytics.py -v

# Run specific test class
pytest tests/api/test_workspace_analytics.py::TestWorkspaceAnalyzer -v

# Run with coverage
pytest tests/api/test_workspace_analytics.py --cov=backend.app.services.workspace_analyzer --cov-report=html
```

---

## Migration

### Applying Migration

```bash
cd backend
alembic upgrade head
```

### Migration File

`27e7df56256c_add_workspace_insights_and_cleanup_.py`

Creates:
- `workspace_insights` table
- `workspace_cleanup_logs` table
- Indexes on user_id for both tables
- Foreign key relationships with cascade delete

---

## Monitoring

### Key Metrics

- **Analysis duration**: Average time to analyze workspace
- **Files per user**: Distribution of file counts
- **Storage per user**: Distribution of storage usage
- **Cleanup operations**: Count by operation type
- **Error rate**: Failed operations / total operations

### Recommended Alerts

- Analysis duration > 2 minutes (potential timeout)
- Error rate > 5% (Drive API issues)
- Cleanup operations > 1000/day (potential abuse)

---

## Related Documentation

- [Google Drive API Documentation](https://developers.google.com/drive/api/v3/about-sdk)
- [OAuth Token Management](./ENHANCED_OAUTH.md)
- [API Rate Limiting](./API_RATE_LIMITING.md)
- [Database Migrations](./DATABASE_MIGRATIONS.md)

---

## Support

For issues or questions:

- **GitHub**: [openclaw/my-superagent](https://github.com/openclaw/my-superagent)
- **Docs**: [docs.agenthq.com](https://docs.agenthq.com)
- **Email**: support@agenthq.com

---

**Sprint 16 Completion**: Smart Workspace Manager ✅  
**Next**: OAuth Scope Refinement (Sprint 16 P3)
