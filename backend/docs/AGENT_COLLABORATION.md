# Multi-Agent Workflow Orchestration

## Overview

The Agent Coordinator Service enables multiple agents to collaborate on complex tasks by chaining them together in workflows. This allows for sophisticated automation pipelines that combine research, document creation, data analysis, and presentation generation.

## Architecture

### Core Components

1. **Agent Protocols** (`backend/app/agents/protocols.py`)
   - `AgentMessage`: Message passing between agents
   - `AgentResponse`: Agent execution results
   - `WorkflowStep`: Single step in a workflow
   - `WorkflowDefinition`: Complete workflow specification
   - `WorkflowResult`: Execution outcome

2. **Agent Coordinator** (`backend/app/agents/coordinator.py`)
   - Orchestrates workflow execution
   - Handles dependency resolution (topological sort)
   - Manages error handling and retries
   - Publishes messages to Redis for observability

3. **Workflow Registry** (`backend/app/workflows/__init__.py`)
   - Pre-defined workflow templates
   - Factory functions for creating workflows

4. **Database Model** (`backend/app/models/workflow_execution.py`)
   - Tracks workflow execution history
   - Stores inputs, outputs, and timing data

5. **API Endpoints** (`backend/app/api/v1/workflows.py`)
   - List workflows: `GET /api/v1/workflows`
   - Execute workflow: `POST /api/v1/workflows/execute`
   - Check status: `GET /api/v1/workflows/{execution_id}/status`
   - View history: `GET /api/v1/workflows/history`

## Available Workflows

### 1. Research to Spreadsheet (`research_to_sheets`)

**Description**: Research a topic and automatically create a formatted Google Sheet

**Steps**:
1. Research Agent: Extract structured data from web sources
2. Sheets Agent: Create spreadsheet with formatting and charts

**Example Input**:
```json
{
  "query": "AI companies 2026"
}
```

**Output**: Google Sheet with company data, funding, and stage

---

### 2. Research to Document (`research_to_docs`)

**Description**: Research a topic and generate a professional report in Google Docs

**Steps**:
1. Research Agent: Comprehensive research with multiple sources
2. Docs Agent: Create formatted report with citations

**Example Input**:
```json
{
  "query": "Quantum computing trends",
  "report_style": "academic"
}
```

**Output**: Professional Google Doc with table of contents and citations

---

### 3. Full Research Pipeline (`full_pipeline`)

**Description**: Complete research workflow with spreadsheet and presentation

**Steps**:
1. Research Agent: Comprehensive data extraction
2. Sheets Agent: Create data tables and charts
3. Slides Agent: Generate presentation with key findings

**Example Input**:
```json
{
  "query": "Electric vehicle market 2026",
  "include_charts": true,
  "presentation_theme": "modern"
}
```

**Output**: Research report, spreadsheet, and presentation slides

## Usage

### API Example

```bash
# List available workflows
curl -X GET "http://localhost:8000/api/v1/workflows" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Execute workflow
curl -X POST "http://localhost:8000/api/v1/workflows/execute" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "research_to_sheets",
    "inputs": {
      "query": "AI companies 2026"
    }
  }'

# Check status
curl -X GET "http://localhost:8000/api/v1/workflows/{execution_id}/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Python SDK Example

```python
from app.workflows import get_workflow
from app.agents.coordinator import AgentCoordinator

# Get workflow
workflow = get_workflow("research_to_sheets")

# Execute
coordinator = AgentCoordinator(redis_client, agent_registry)
result = await coordinator.execute_workflow(
    workflow=workflow,
    initial_inputs={"query": "AI companies 2026"},
    user_id=user_id,
)

print(f"Status: {result.status}")
print(f"Output: {result.final_output}")
```

## Features

### Dependency Resolution
- Workflows are executed in dependency order using topological sort
- Circular dependencies are detected and rejected

### Error Handling
- **Stop**: Workflow stops on first error (default)
- **Skip**: Continue to next step if step fails
- **Retry**: Automatic retries with configurable max attempts

### Input Mapping
- Data flows between steps via `input_mapping`
- Map output keys from one step to input keys of the next

```python
step2 = WorkflowStep(
    agent=AgentRole.SHEETS,
    task_description="Create spreadsheet",
    dependencies=[step1.step_id],
    input_mapping={
        "data": "results",  # Map step1.results to step2.data
    }
)
```

### Observability
- All messages published to Redis channels
- Real-time monitoring via Redis Pub/Sub
- Database tracking for historical analysis

## Database Schema

```sql
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY,
    execution_id VARCHAR(36) UNIQUE NOT NULL,
    workflow_id VARCHAR(100) NOT NULL,
    workflow_name VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL,  -- pending/running/completed/failed
    current_step VARCHAR(36),
    initial_inputs JSONB NOT NULL,
    step_results JSONB NOT NULL,
    final_output JSONB,
    error TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    metadata JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_workflow_user ON workflow_executions(user_id);
CREATE INDEX idx_workflow_status ON workflow_executions(status);
```

## Creating Custom Workflows

```python
from app.agents.protocols import AgentRole, WorkflowDefinition, WorkflowStep

def create_custom_workflow() -> WorkflowDefinition:
    step1 = WorkflowStep(
        agent=AgentRole.RESEARCH,
        task_description="Research the topic",
        dependencies=[],
    )
    
    step2 = WorkflowStep(
        agent=AgentRole.DOCS,
        task_description="Create document",
        dependencies=[step1.step_id],
        input_mapping={"data": "results"},
        error_handling="stop",
        max_retries=3,
    )
    
    return WorkflowDefinition(
        name="Custom Workflow",
        description="My custom workflow",
        steps=[step1, step2],
        initial_inputs={"query": ""},
        metadata={"category": "custom"},
    )
```

## Future Enhancements

### Phase 3 Roadmap
- [x] Agent coordinator service ✅
- [x] Multi-agent workflows (3 examples) ✅
- [x] Workflow status tracking ✅
- [ ] Celery task integration (async execution)
- [ ] Visual workflow builder (UI)
- [ ] Conditional branching
- [ ] Parallel step execution
- [ ] Workflow templates marketplace

### Production Considerations
- Move workflow execution to Celery for async processing
- Add webhook notifications for workflow completion
- Implement workflow versioning
- Add cost estimation before execution
- Create workflow debugging tools

## Testing

### Unit Tests
```bash
pytest tests/agents/test_coordinator.py -v
pytest tests/agents/test_protocols.py -v
```

### Integration Tests
```bash
pytest tests/workflows/test_multi_agent_workflows.py -v
```

## Migration

```bash
cd backend
alembic upgrade head
```

## Performance

- **Average workflow duration**: 30-180 seconds (depends on complexity)
- **Parallel execution**: Not yet supported (coming in Phase 3)
- **Redis overhead**: Minimal (<1ms per message)

## Security

- All workflows require OAuth authentication
- Users can only view their own execution history
- Workflow inputs/outputs stored encrypted at rest
- Rate limiting applied per user

## Support

For issues or questions:
- GitHub: https://github.com/your-org/agenthq
- Docs: See `docs/AGENT_COLLABORATION.md`
- API Docs: http://localhost:8000/docs#/workflows

---

**Last Updated**: 2026-03-02  
**Sprint**: Sprint 11 - Agent Collaboration Foundation  
**Status**: ✅ Complete (Phase 1)
