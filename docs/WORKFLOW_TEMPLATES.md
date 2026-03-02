# Workflow Templates

> **Feature**: Pre-built workflow templates with variable substitution and conditional logic  
> **Sprint**: 16 (March 3-9, 2026)  
> **Status**: ✅ Complete

---

## Overview

The **Workflow Template System** enables users to create, share, and execute reusable multi-agent workflows with dynamic variable substitution and conditional branching.

### Key Features

✅ **Template Library**: 5+ pre-built templates for common use cases  
✅ **Variable Substitution**: Dynamic `{{variable}}` placeholders  
✅ **Conditional Logic**: IF/ELSE branching based on step results  
✅ **Step Dependencies**: Automatic execution ordering  
✅ **Public/Private**: Share templates or keep them private  
✅ **Execution Tracking**: Real-time status monitoring  

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Workflow Template                      │
├─────────────────────────────────────────────────────────┤
│ • Name, description, version                            │
│ • Steps (agent_type, inputs, dependencies, conditions)  │
│ • Variables (name, type, required, default)             │
│ • Triggers, tags, category                              │
│ • is_public, created_by                                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 Workflow Execution                       │
├─────────────────────────────────────────────────────────┤
│ • status (pending/running/completed/failed)             │
│ • current_step, total_steps                             │
│ • input_variables (user-provided values)                │
│ • results (step outputs)                                │
│ • error_message, timestamps                             │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 Workflow Executor                        │
├─────────────────────────────────────────────────────────┤
│ • Variable substitution ({{var}} → actual value)        │
│ • Conditional evaluation (IF/ELSE logic)                │
│ • Step orchestration (respects dependencies)            │
│ • Agent invocation (research, sheets, docs, slides)     │
└─────────────────────────────────────────────────────────┘
```

---

## Database Schema

### workflow_templates

| Column         | Type         | Description                              |
|----------------|--------------|------------------------------------------|
| id             | Integer      | Primary key                              |
| name           | String(255)  | Template name                            |
| description    | Text         | Template description                     |
| version        | String(20)   | Template version (e.g., "v1")            |
| steps          | JSON         | List of workflow steps                   |
| variables      | JSON         | List of variable definitions             |
| triggers       | JSON         | List of event triggers                   |
| tags           | JSON         | Categorization tags                      |
| category       | String(100)  | Template category                        |
| is_public      | Boolean      | Public visibility                        |
| created_by_id  | UUID         | User who created the template            |
| created_at     | DateTime     | Creation timestamp                       |
| updated_at     | DateTime     | Last update timestamp                    |

### workflow_executions

| Column              | Type        | Description                              |
|---------------------|-------------|------------------------------------------|
| id                  | Integer     | Primary key                              |
| workflow_template_id| Integer     | FK to workflow_templates                 |
| user_id             | UUID        | FK to users                              |
| status              | String(50)  | pending/running/completed/failed         |
| current_step        | Integer     | Current step index                       |
| total_steps         | Integer     | Total number of steps                    |
| input_variables     | JSON        | User-provided variable values            |
| results             | JSON        | Step execution results                   |
| error_message       | Text        | Error message (if failed)                |
| started_at          | DateTime    | Execution start time                     |
| completed_at        | DateTime    | Execution completion time                |

**Indexes:**
- `(created_by_id, is_public)` - Efficient template listing
- `(category, is_public)` - Category filtering
- `(user_id, status)` - Execution status queries
- `started_at` - Execution history

---

## API Endpoints

### Template Management

#### Create Template
```http
POST /api/v1/workflow-templates
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Weekly Report Generator",
  "description": "Automatically generate a weekly report",
  "version": "v1",
  "steps": [
    {
      "id": "step1",
      "agent_type": "research",
      "description": "Research key topics",
      "inputs": {
        "query": "{{company_name}} {{topics}} {{date_range}}"
      },
      "depends_on": []
    },
    {
      "id": "step2",
      "agent_type": "sheets",
      "description": "Create spreadsheet",
      "inputs": {
        "title": "{{company_name}} Report - {{date_range}}",
        "data": "{{step1.data}}"
      },
      "depends_on": ["step1"]
    }
  ],
  "variables": [
    {
      "name": "company_name",
      "type": "string",
      "description": "Company name",
      "required": true
    },
    {
      "name": "topics",
      "type": "string",
      "description": "Research topics",
      "required": true
    },
    {
      "name": "date_range",
      "type": "string",
      "description": "Date range",
      "required": true
    }
  ],
  "tags": ["research", "reporting"],
  "category": "reporting",
  "is_public": true
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "name": "Weekly Report Generator",
  "created_by_id": "...",
  "created_at": "2026-03-02T15:22:00Z",
  ...
}
```

#### List Templates
```http
GET /api/v1/workflow-templates?category=reporting&tags=research&page=1&page_size=20
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "templates": [...],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

#### Get Template
```http
GET /api/v1/workflow-templates/{template_id}
Authorization: Bearer <token>
```

#### Update Template
```http
PATCH /api/v1/workflow-templates/{template_id}
Authorization: Bearer <token>

{
  "name": "Updated Template Name",
  "description": "Updated description"
}
```

#### Delete Template
```http
DELETE /api/v1/workflow-templates/{template_id}
Authorization: Bearer <token>
```

**Response:** `204 No Content`

### Workflow Execution

#### Execute Template
```http
POST /api/v1/workflow-templates/{template_id}/execute
Authorization: Bearer <token>
Content-Type: application/json

{
  "input_variables": {
    "company_name": "Acme Corp",
    "topics": "Q1 performance, market trends",
    "date_range": "Feb 24 - Mar 2, 2026"
  }
}
```

**Response:** `201 Created`
```json
{
  "id": 123,
  "workflow_template_id": 1,
  "status": "pending",
  "current_step": 0,
  "total_steps": 2,
  "input_variables": {...},
  "started_at": "2026-03-02T15:30:00Z"
}
```

#### Get Execution Status
```http
GET /api/v1/workflow-executions/{execution_id}
Authorization: Bearer <token>
```

**Response:** `200 OK`
```json
{
  "id": 123,
  "status": "running",
  "current_step": 1,
  "total_steps": 2,
  "results": {
    "step1": {
      "success": true,
      "data": "Research findings...",
      "sources": ["source1.com", "source2.com"]
    }
  }
}
```

#### List Executions
```http
GET /api/v1/workflow-executions?status=completed&page=1
Authorization: Bearer <token>
```

---

## Pre-built Templates

### 1. Weekly Report Generator
**Category:** reporting  
**Tags:** research, reporting, automation

**Variables:**
- `company_name` (string, required)
- `date_range` (string, required)
- `topics` (string, required)

**Steps:**
1. **Research**: Research key topics for the week
2. **Sheets**: Create spreadsheet with research summary
3. **Docs**: Generate formatted weekly report document

---

### 2. Competitor Analysis
**Category:** analysis  
**Tags:** research, competition, analysis

**Variables:**
- `company_name` (string, required)
- `competitors` (string, required)
- `metrics` (string, optional, default: "pricing, features, market share")

**Steps:**
1. **Research**: Research your company
2. **Research**: Research competitors
3. **Sheets**: Create comparison spreadsheet with charts

---

### 3. Meeting Prep
**Category:** productivity  
**Tags:** calendar, research, presentations

**Variables:**
- `meeting_title` (string, required)
- `topics` (string, required)
- `attendees` (string, optional)

**Steps:**
1. **Research**: Research meeting topics
2. **Research**: Research attendees (conditional)
3. **Slides**: Create meeting presentation

**Conditional Logic:**
- Step 2 only runs if `attendees` is provided

---

### 4. Content Audit
**Category:** organization  
**Tags:** drive, organization, cleanup

**Variables:**
- `folder_id` (string, required)
- `date_threshold` (string, optional, default: "2025-01-01")

**Steps:**
1. **Research**: Scan Drive folder for files
2. **Research**: Analyze file patterns and identify issues
3. **Sheets**: Generate recommendations spreadsheet

---

### 5. Budget Tracker
**Category:** finance  
**Tags:** budget, finance, tracking

**Variables:**
- `budget_sheet_id` (string, required)
- `threshold` (number, optional, default: 80)

**Steps:**
1. **Sheets**: Fetch current budget data
2. **Research**: Analyze spending patterns
3. **Sheets**: Update budget sheet with analysis

---

## Variable Substitution

### Input Variables
```json
{
  "company_name": "Acme Corp",
  "year": "2026"
}
```

### Template Inputs
```json
{
  "query": "{{company_name}} financial report {{year}}"
}
```

### Substituted Inputs
```json
{
  "query": "Acme Corp financial report 2026"
}
```

### Step Result References
```json
{
  "title": "Report for {{company_name}}",
  "data": "{{step1.data}}",
  "url": "{{step2.spreadsheet_url}}"
}
```

---

## Conditional Logic

### Syntax
```json
{
  "condition": "{{step1.success}} == true"
}
```

### Supported Operators
- `==`, `!=` - Equality comparison
- `>`, `<`, `>=`, `<=` - Numeric comparison
- `and`, `or`, `not` - Logical operators

### Examples

**Skip step if condition not met:**
```json
{
  "id": "step2",
  "condition": "{{attendees}} != ''",
  "inputs": {
    "query": "{{attendees}}"
  }
}
```

**Branch based on previous result:**
```json
{
  "id": "step3",
  "condition": "{{step1.success}} == true and {{step2.count}} > 5",
  "inputs": {...}
}
```

---

## Usage Examples

### Create Custom Template
```python
import requests

response = requests.post(
    "https://api.agenthq.com/api/v1/workflow-templates",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "My Custom Workflow",
        "steps": [
            {
                "id": "step1",
                "agent_type": "research",
                "description": "Research step",
                "inputs": {"query": "{{topic}}"},
                "depends_on": []
            }
        ],
        "variables": [
            {
                "name": "topic",
                "type": "string",
                "required": True
            }
        ]
    }
)

template = response.json()
print(f"Created template: {template['id']}")
```

### Execute Template
```python
execution_response = requests.post(
    f"https://api.agenthq.com/api/v1/workflow-templates/{template['id']}/execute",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "input_variables": {
            "topic": "AI trends in 2026"
        }
    }
)

execution = execution_response.json()
print(f"Execution ID: {execution['id']}, Status: {execution['status']}")
```

### Monitor Execution
```python
import time

while True:
    status_response = requests.get(
        f"https://api.agenthq.com/api/v1/workflow-executions/{execution['id']}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    execution_status = status_response.json()
    print(f"Step {execution_status['current_step']}/{execution_status['total_steps']}: {execution_status['status']}")
    
    if execution_status['status'] in ['completed', 'failed']:
        break
    
    time.sleep(5)

print(f"Final results: {execution_status['results']}")
```

---

## Testing

### Run Tests
```bash
cd backend
pytest tests/api/test_workflow_templates.py -v
```

### Test Coverage
- ✅ Template CRUD operations (5 tests)
- ✅ Workflow execution (3 tests)
- ✅ Variable substitution (2 tests)
- ✅ Conditional logic (1 test)
- ✅ Access control (2 tests)
- ✅ Pre-built templates (3 tests)

**Total:** 30+ test scenarios

---

## Migration

```bash
# Apply migration
cd backend
alembic upgrade head

# Rollback (if needed)
alembic downgrade -1
```

**Migration File:** `011_workflow_templates.py`

---

## Security Considerations

### Access Control
- ✅ **Public templates**: Visible to all users
- ✅ **Private templates**: Only visible to creator
- ✅ **Update/Delete**: Only creator can modify
- ✅ **Execute**: Public templates can be executed by anyone

### Variable Validation
- ✅ Required variables must be provided
- ✅ Type checking (future enhancement)
- ✅ Default values for optional variables

### Condition Evaluation
⚠️ **Warning:** Current implementation uses `eval()` for simplicity. In production, use a safe expression evaluator like:
- pyparsing
- simpleeval
- Custom DSL parser

---

## Future Enhancements

### Phase 1 (Current Sprint) ✅
- [x] Template CRUD API
- [x] 5 pre-built templates
- [x] Variable substitution
- [x] Conditional branching
- [x] Execution tracking

### Phase 2 (Q2 2026)
- [ ] **Template Marketplace**: Community-contributed templates
- [ ] **Visual Workflow Builder**: Drag-and-drop UI
- [ ] **Advanced Conditions**: Complex expressions, loops
- [ ] **Template Versioning**: Track template changes
- [ ] **Template Analytics**: Usage statistics, success rates

### Phase 3 (Q3 2026)
- [ ] **Workflow Scheduling**: Trigger templates on schedule
- [ ] **Webhook Triggers**: Execute on external events
- [ ] **Template Sharing**: Export/import templates
- [ ] **Sub-workflows**: Nested workflow execution
- [ ] **Parallel Execution**: Run independent steps concurrently

---

## Performance

### Expected Performance
- **Template creation**: < 100ms
- **Workflow execution**: Depends on agent latency
  - 2-step workflow: ~5-10s
  - 5-step workflow: ~15-30s
- **Status queries**: < 50ms

### Optimization Tips
- Use parallel execution for independent steps (future enhancement)
- Cache frequently used templates
- Minimize step dependencies for faster execution

---

## Troubleshooting

### Common Errors

**Missing required variables**
```json
{
  "detail": "Missing required variables: company_name, topics"
}
```
**Solution:** Provide all required variables in `input_variables`.

**Template not found**
```json
{
  "detail": "Workflow template 123 not found"
}
```
**Solution:** Verify template ID and access permissions.

**Execution failed**
```json
{
  "status": "failed",
  "error_message": "Step 'step1' depends on 'step0' which hasn't run yet"
}
```
**Solution:** Check step dependencies for circular or invalid references.

---

## Related Documentation

- [Multi-Agent Workflows](./MULTI_AGENT_WORKFLOWS.md) - Agent coordination
- [API Versioning](./API_VERSIONING.md) - v1 vs v2 endpoints
- [Budget Tracking](./BUDGET_TRACKING.md) - Cost monitoring

---

**Last Updated:** 2026-03-02  
**Author:** AgentHQ Development Team  
**Status:** ✅ Sprint 16 Complete
