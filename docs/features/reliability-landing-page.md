# Reliability Landing Page (Feature #276)

## Overview

The **Reliability Landing Page** is an AI-powered failure recovery system that helps users quickly recover from task failures. Instead of showing a generic error message, AgentHQ now provides 1-3 actionable recovery suggestions ranked by confidence and success probability.

## Key Features

### 1. **Smart Recovery Suggestions**
When a task fails, the system automatically analyzes:
- Error message and category
- Task type and context
- User permissions
- Historical success patterns

And generates targeted suggestions such as:
- **Grant missing permissions** - Fix permission errors with one click
- **Simplify and retry** - Break down complex tasks
- **Retry with delay** - Handle rate limits intelligently
- **Contact support** - Escalate critical failures

### 2. **Confidence Scoring**
Each suggestion includes:
- **Confidence score** (0-100): How likely this will work
- **Estimated success rate**: Based on historical data
- **Priority ranking**: Most likely solutions first

### 3. **One-Click Recovery**
Users can execute recovery actions directly from the failure screen:
- Retry with modified parameters
- Fix permissions via OAuth re-auth
- Apply simplified prompts
- Schedule delayed retry

### 4. **Recovery Analytics**
Track which recovery strategies work:
- Success rate per suggestion type
- User selection patterns
- Time to recovery
- Most common failure types

## API Endpoints

### GET `/api/v1/recovery/tasks/{task_id}/suggestions`
Get recovery suggestions for a failed task.

**Response:**
```json
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "task_status": "failed",
  "error_message": "Permission denied: 403 Forbidden",
  "suggestions": [
    {
      "id": "suggestion-uuid",
      "type": "fix_permissions",
      "title": "Grant missing permissions",
      "description": "This task failed because it couldn't access Google Workspace resources...",
      "confidence_score": 85,
      "estimated_success_rate": 90,
      "priority": 1,
      "action_payload": {
        "action": "redirect_to_permissions",
        "required_scopes": [
          "https://www.googleapis.com/auth/documents",
          "https://www.googleapis.com/auth/drive.file"
        ]
      }
    }
  ]
}
```

### POST `/api/v1/recovery/suggestions/{suggestion_id}/select`
Mark a suggestion as selected by the user.

**Response:**
```json
{
  "success": true,
  "suggestion": { /* suggestion object */ },
  "action_payload": {
    "action": "retry",
    "task_id": "..."
  }
}
```

### GET `/api/v1/recovery/tasks/{task_id}/recovery-status`
Get comprehensive recovery status including chain progress and analytics.

**Response:**
```json
{
  "task": {
    "id": "...",
    "status": "failed",
    "error_message": "..."
  },
  "recovery": {
    "suggestions": [ /* array */ ],
    "suggestions_count": 3,
    "has_recovery_options": true
  },
  "chain": {
    "current_step": 1,
    "total_steps": 3,
    "remaining": 2
  },
  "analytics": {
    "historical_success_rate": 75,
    "similar_tasks_count": 10
  }
}
```

## Database Schema

### `recovery_suggestions` table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| task_id | UUID | Failed task reference |
| user_id | UUID | Task owner |
| suggestion_type | ENUM | retry, fix_permissions, simplify_prompt, etc. |
| title | STRING(200) | Short action title |
| description | TEXT | Detailed explanation |
| confidence_score | INTEGER | 0-100 confidence |
| action_payload | JSON | Action parameters |
| error_category | STRING(100) | permission_denied, timeout, rate_limit, etc. |
| estimated_success_rate | INTEGER | 0-100 success probability |
| priority | INTEGER | 1=highest, 3=lowest |
| was_selected | INTEGER | 0=no, 1=yes |
| selection_timestamp | INTEGER | When user clicked |
| outcome_success | INTEGER | 0=failed, 1=succeeded |
| created_at | INTEGER | Unix timestamp |
| expires_at | INTEGER | Expiration (24h default) |

### Indexes
- `task_id` - Fast lookup by task
- `user_id` - User's recovery history
- `suggestion_type` - Analytics by type
- `error_category` - Group by error type

## Implementation Details

### Error Categorization
Errors are automatically categorized into:
- `permission_denied` - 403 errors, auth issues
- `timeout` - Task took too long
- `rate_limit` - API quota exceeded
- `resource_not_found` - 404 errors
- `internal_error` - 500 errors
- `invalid_request` - 400 errors
- `unknown` - Uncategorized

### Scope Inference
For permission errors, the system infers required Google API scopes:
- **Document tasks** → `documents`, `drive.file`
- **Spreadsheet tasks** → `spreadsheets`, `drive.file`
- **Presentation tasks** → `presentations`, `drive.file`

### Suggestion Expiration
Suggestions expire after 24 hours to keep recovery options relevant. Expired suggestions are not shown to users.

## Usage Examples

### 1. Permission Error Recovery
```python
# User creates a document task
task = create_task(user, "Create quarterly report")

# Task fails with permission error
task.status = TaskStatus.FAILED
task.error_message = "Permission denied: 403 Forbidden"

# System generates suggestions
service = RecoverySuggestionService(db)
suggestions = await service.generate_suggestions(task, user)

# User sees: "Grant missing permissions" (85% confidence)
# User clicks → redirected to OAuth consent screen
```

### 2. Timeout Recovery
```python
# Complex research task times out
task.error_message = "Task timed out after 60 seconds"

# System suggests: "Simplify and retry"
# Suggested prompt: Shorter, more focused version
# User accepts → new task created with simplified prompt
```

### 3. Rate Limit Handling
```python
# Bulk operation hits rate limit
task.error_message = "Rate limit exceeded: 429"

# System suggests: "Retry in 10 minutes"
# User clicks → task scheduled for retry with delay
```

## Frontend Integration

### Desktop App
Add a recovery screen component:

```javascript
// components/RecoveryLanding.jsx
function RecoveryLanding({ taskId }) {
  const { data } = useFetch(`/api/v1/recovery/tasks/${taskId}/suggestions`);
  
  return (
    <div className="recovery-page">
      <h2>Task Failed - Here's How to Fix It</h2>
      <ErrorSummary error={data.error_message} />
      
      <div className="suggestions">
        {data.suggestions.map(suggestion => (
          <SuggestionCard
            key={suggestion.id}
            suggestion={suggestion}
            onSelect={() => handleSelect(suggestion)}
          />
        ))}
      </div>
      
      <RecoveryProgress task={data.task} />
    </div>
  );
}
```

### Mobile App
Flutter recovery widget:

```dart
class RecoveryScreen extends StatelessWidget {
  final String taskId;
  
  @override
  Widget build(BuildContext context) {
    return FutureBuilder<RecoveryData>(
      future: api.getRecoverySuggestions(taskId),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return LoadingSpinner();
        
        return Column(
          children: [
            ErrorBanner(message: snapshot.data.errorMessage),
            ...snapshot.data.suggestions.map(
              (s) => SuggestionTile(
                suggestion: s,
                onTap: () => _handleSelect(s),
              )
            ),
          ],
        );
      },
    );
  }
}
```

## Testing

Run the test suite:
```bash
cd backend
.venv/bin/pytest tests/test_recovery_suggestions.py -v
```

### Test Coverage
- ✅ Permission error suggestions
- ✅ Timeout error suggestions
- ✅ Rate limit suggestions
- ✅ Error categorization
- ✅ Scope inference
- ✅ Suggestion expiration
- ✅ Selection tracking
- ✅ API endpoints

## Future Enhancements

### 1. **ML-Powered Suggestions**
Train a model on historical recovery success to improve suggestion ranking.

### 2. **Template-Based Recovery**
Suggest alternative templates for failed tasks:
- "Try the 'Simple Report' template instead"
- "This works better with 'Data Analysis' template"

### 3. **Chain-Aware Recovery**
For multi-step chains:
- Show progress: "Step 2 of 5 failed"
- Offer partial recovery: "Complete steps 1-3, skip 4"
- Resume from checkpoint

### 4. **Proactive Failure Prevention**
Analyze task before execution:
- "This might fail - missing permissions"
- "Large scope - consider splitting"
- "Rate limit warning - delay recommended"

## Metrics to Track

### Key Performance Indicators
- **Recovery Success Rate**: % of failures that successfully recover
- **Time to Recovery**: Average time from failure to completion
- **Suggestion Selection Rate**: Which suggestions users choose most
- **Recovery Abandonment**: % of users who give up after failure

### Analytics Queries
```sql
-- Most common failure types
SELECT error_category, COUNT(*) 
FROM recovery_suggestions 
GROUP BY error_category 
ORDER BY COUNT(*) DESC;

-- Most effective recovery strategies
SELECT suggestion_type, 
       AVG(outcome_success) as success_rate,
       COUNT(*) as total_uses
FROM recovery_suggestions 
WHERE was_selected = 1
GROUP BY suggestion_type;

-- Average time to recovery
SELECT AVG(selection_timestamp - created_at) as avg_recovery_time_seconds
FROM recovery_suggestions 
WHERE was_selected = 1;
```

## Impact

### Expected Metrics (from Idea #276)
- **Retry abandonment**: -20%
- **First retry success rate**: +30%
- **User trust/retention**: Improved confidence in system reliability

### User Experience Benefits
- ✅ Clear next steps after failure
- ✅ No manual debugging required
- ✅ Reduced support tickets
- ✅ Faster recovery time
- ✅ Improved trust in automation

---

**Feature Status**: ✅ Implemented  
**Issue**: #276 (Idea #276: Reliability Landing Page)  
**Sprint**: Sprint 3  
**Author**: Dev Codex  
**Date**: 2026-02-25
