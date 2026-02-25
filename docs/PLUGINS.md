# Plugin System Documentation

## Overview

The AgentHQ Plugin System enables integration with external tools and services like Notion, Jira, and Confluence. Plugins extend the platform's capabilities beyond Google Workspace.

## Architecture

### Core Components

1. **Plugin Base** (`app/plugins/base.py`)
   - Abstract `Plugin` class
   - `PluginConfig` for configuration
   - `PluginRegistry` for lifecycle management

2. **Plugin Implementations** (e.g., `app/plugins/notion_plugin.py`)
   - Inherit from `Plugin`
   - Implement authentication and capabilities
   - Provide service-specific methods

3. **API Endpoints** (`app/api/v1/plugins.py`)
   - Configure plugins
   - Check connection status
   - Execute plugin actions

## Supported Plugins

### Notion

**Capabilities:**
- `create_page` — Create new pages
- `search` — Search across workspace
- `query_database` — Query databases with filters
- `append_blocks` — Add content to pages
- `get_page` — Retrieve page properties
- `update_page` — Modify existing pages

**Configuration:**
```bash
# Set Notion API key
export NOTION_API_KEY="secret_..."
```

## API Usage

### 1. List Available Plugins

```http
GET /api/v1/plugins
Authorization: Bearer {jwt_token}
```

**Response:**
```json
{
  "plugins": ["notion"],
  "enabled": ["notion"]
}
```

### 2. Configure a Plugin

```http
POST /api/v1/plugins/notion/configure
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "api_key": "secret_NOTION_API_KEY",
  "config": {}
}
```

**Response:**
```json
{
  "name": "notion",
  "connected": true,
  "message": "Connection successful",
  "details": {
    "user_id": "abc123",
    "bot": {...}
  }
}
```

### 3. Check Plugin Status

```http
GET /api/v1/plugins/notion/status
Authorization: Bearer {jwt_token}
```

**Response:**
```json
{
  "name": "notion",
  "connected": true,
  "message": "Connection successful",
  "details": {...}
}
```

### 4. Execute Plugin Actions

#### Notion: Search

```http
POST /api/v1/plugins/notion/action
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "action": "search",
  "parameters": {
    "query": "meeting notes",
    "filter_type": "page"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": [
    {
      "id": "page_123",
      "object": "page",
      "properties": {...}
    }
  ]
}
```

#### Notion: Create Page

```http
POST /api/v1/plugins/notion/action
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "action": "create_page",
  "parameters": {
    "parent_id": "workspace_id_or_page_id",
    "title": "Meeting Notes",
    "content": [
      {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
          "rich_text": [
            {"type": "text", "text": {"content": "Discussion topics..."}}
          ]
        }
      }
    ]
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "id": "new_page_123",
    "object": "page",
    "created_time": "2026-02-25T00:00:00.000Z"
  }
}
```

#### Notion: Query Database

```http
POST /api/v1/plugins/notion/action
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "action": "query_database",
  "parameters": {
    "database_id": "db_abc123",
    "filter_conditions": {
      "property": "Status",
      "select": {"equals": "In Progress"}
    },
    "sorts": [
      {"property": "Priority", "direction": "descending"}
    ]
  }
}
```

## Python SDK Example

```python
import httpx

BASE_URL = "https://api.agenthq.dev/api/v1"
JWT_TOKEN = "your_jwt_token"

headers = {"Authorization": f"Bearer {JWT_TOKEN}"}

# 1. Configure Notion plugin
config_response = httpx.post(
    f"{BASE_URL}/plugins/notion/configure",
    headers=headers,
    json={"api_key": "secret_NOTION_KEY"}
)
print(config_response.json())

# 2. Search Notion workspace
search_response = httpx.post(
    f"{BASE_URL}/plugins/notion/action",
    headers=headers,
    json={
        "action": "search",
        "parameters": {"query": "project roadmap"}
    }
)
results = search_response.json()["result"]

# 3. Create a new page
create_response = httpx.post(
    f"{BASE_URL}/plugins/notion/action",
    headers=headers,
    json={
        "action": "create_page",
        "parameters": {
            "parent_id": "workspace_123",
            "title": "Sprint Retrospective",
            "content": [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "What went well"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": "Completed all stories"}}]
                    }
                }
            ]
        }
    }
)
new_page = create_response.json()["result"]
print(f"Created page: {new_page['id']}")
```

## Agent Integration Example

Plugins can be used within agents for automated workflows:

```python
from app.plugins import NotionPlugin, registry

# Configure plugin (in agent initialization)
notion = NotionPlugin(api_key=os.getenv("NOTION_API_KEY"))
await notion.authenticate()
registry.register(notion)

# Use in agent task
async def create_meeting_notes(agent_prompt: str):
    # 1. Generate notes with LLM
    notes_content = await agent.llm.invoke(agent_prompt)
    
    # 2. Search for parent page
    notion_plugin = registry.get("notion")
    search_results = await notion_plugin.search("Team Meetings")
    parent_id = search_results[0]["id"]
    
    # 3. Create Notion page
    page = await notion_plugin.create_page(
        parent_id=parent_id,
        title=f"Meeting Notes - {datetime.now().strftime('%Y-%m-%d')}",
        content=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": notes_content}}]
                }
            }
        ]
    )
    
    return f"Created notes: {page['url']}"
```

## Adding New Plugins

To add a new plugin (e.g., Jira):

### 1. Create Plugin Class

```python
# app/plugins/jira_plugin.py
from .base import Plugin, PluginConfig, PluginType
from jira import JIRA

class JiraPlugin(Plugin):
    def __init__(self, api_key: str, server_url: str):
        config = PluginConfig(
            name="jira",
            display_name="Jira",
            type=PluginType.ISSUE_TRACKING,
            api_key=api_key,
            config={"server": server_url}
        )
        super().__init__(config)
    
    async def authenticate(self) -> bool:
        try:
            self.client = JIRA(
                server=self.config.config["server"],
                token_auth=self.config.api_key
            )
            return True
        except Exception:
            return False
    
    async def test_connection(self) -> Dict[str, Any]:
        # Implementation...
        pass
    
    async def get_capabilities(self) -> List[str]:
        return ["create_issue", "search_issues", "update_issue"]
    
    async def create_issue(self, project: str, summary: str, **kwargs):
        # Implementation...
        pass
```

### 2. Register in `__init__.py`

```python
# app/plugins/__init__.py
from .jira_plugin import JiraPlugin

__all__ = [..., "JiraPlugin"]
```

### 3. Update API Endpoint

```python
# app/api/v1/plugins.py
@router.post("/{plugin_name}/configure")
async def configure_plugin(...):
    if plugin_name.lower() == "jira":
        plugin = JiraPlugin(
            api_key=config.api_key,
            server_url=config.config.get("server_url")
        )
    # ...
```

### 4. Add Tests

```python
# tests/test_plugins.py
class TestJiraPlugin:
    @pytest.mark.asyncio
    async def test_jira_authentication(self):
        # Test implementation...
        pass
```

## Error Handling

All plugins handle errors consistently:

### Authentication Errors (401)
```json
{
  "detail": "Authentication failed. Check API key."
}
```

### Plugin Not Found (404)
```json
{
  "detail": "Plugin 'notion' not found or not configured"
}
```

### Unsupported Action (400)
```json
{
  "detail": "Action 'invalid_action' not supported. Available: ['search', 'create_page', ...]"
}
```

### External API Errors (500)
```json
{
  "detail": "Notion API error: rate limit exceeded"
}
```

## Security

### API Key Storage
- API keys are **NOT** stored in the database
- Keys are only held in memory during session
- Use environment variables or secure vaults for production

### Permissions
- Plugin actions require valid JWT token
- Users can only access their own plugin configurations
- Superusers can manage all plugins (future)

## Rate Limiting

Plugins respect external service rate limits:
- **Notion:** 3 requests/second
- **Jira:** Varies by plan
- **Confluence:** 5 requests/second

The plugin system automatically retries with exponential backoff.

## Monitoring

Plugin usage is tracked in audit logs:

```python
# Audit log entry
{
  "event_type": "plugin_action",
  "action": "notion.create_page",
  "user_id": "user_123",
  "resource_id": "new_page_123",
  "timestamp": "2026-02-25T00:00:00Z"
}
```

## Future Plugins

Planned integrations:
- [ ] **Jira** — Issue tracking
- [ ] **Confluence** — Knowledge base
- [ ] **Slack** — Messaging (beyond webhooks)
- [ ] **Linear** — Project management
- [ ] **GitHub** — Code repositories
- [ ] **Salesforce** — CRM

## References

- [Notion API Documentation](https://developers.notion.com/)
- [Plugin Base Class](../app/plugins/base.py)
- [Notion Plugin Implementation](../app/plugins/notion_plugin.py)
- [API Endpoints](../app/api/v1/plugins.py)
