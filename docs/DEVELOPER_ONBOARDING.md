# 🚀 Developer Onboarding Guide

> **Welcome to AgentHQ!** This guide will help you set up your development environment and understand the codebase.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Architecture Overview](#architecture-overview)
4. [Development Workflow](#development-workflow)
5. [Testing](#testing)
6. [Common Tasks](#common-tasks)
7. [Troubleshooting](#troubleshooting)
8. [Resources](#resources)

---

## Prerequisites

Before starting, ensure you have:

- **Python 3.11+** installed
- **Docker** and **Docker Compose** (for PostgreSQL, Redis, Celery)
- **Git** configured with your credentials
- **Google Cloud credentials** (for OAuth, Docs, Sheets, Slides APIs)
- **OpenAI API key** or **Anthropic API key** (for LLM features)

### Recommended Tools

- **VS Code** or **PyCharm** for IDE
- **Postman** or **curl** for API testing
- **DBeaver** or **pgAdmin** for database management
- **Redis Desktop Manager** for Redis debugging

---

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/my-superagent.git
cd my-superagent
```

### 2. Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/agenthq

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic Claude (optional)
ANTHROPIC_API_KEY=sk-ant-...

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# GitHub OAuth (optional)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Microsoft OAuth (optional)
MICROSOFT_CLIENT_ID=your-microsoft-client-id
MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret

# Email (for notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# JWT Secret
SECRET_KEY=your-secret-key-here
```

### 5. Start Infrastructure with Docker

```bash
docker-compose up -d postgres redis
```

### 6. Run Database Migrations

```bash
alembic upgrade head
```

### 7. Start the Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 8. Start Celery Workers (Optional)

In separate terminals:

```bash
# Worker
celery -A app.celery_app worker --loglevel=info

# Beat (for scheduled tasks)
celery -A app.celery_app beat --loglevel=info

# Flower (monitoring UI)
celery -A app.celery_app flower --port=5555
```

### 9. Verify Setup

```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

---

## Architecture Overview

### Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (with SQLAlchemy ORM)
- **Cache**: Redis
- **Task Queue**: Celery with Redis broker
- **LLM**: LangChain with OpenAI/Anthropic
- **APIs**: Google (Docs, Sheets, Slides), GitHub, Microsoft

### Project Structure

```
my-superagent/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # Database connection & session
│   ├── models/              # SQLAlchemy models
│   │   ├── agent.py
│   │   ├── user.py
│   │   ├── oauth_token.py
│   │   └── llm_usage.py
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # API routes
│   │   ├── agents.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   └── oauth.py
│   ├── services/            # Business logic
│   │   ├── agent_service.py
│   │   ├── llm_service.py
│   │   ├── google_docs_agent.py
│   │   ├── google_sheets_agent.py
│   │   └── fact_checking_service.py
│   ├── tasks/               # Celery tasks
│   │   ├── scheduling.py
│   │   ├── email_tasks.py
│   │   └── oauth_tasks.py
│   └── celery_app.py        # Celery configuration
├── alembic/                 # Database migrations
├── docs/                    # Documentation
├── tests/                   # Test suite
├── requirements.txt
├── docker-compose.yml
└── .env
```

### Key Components

#### 1. **API Layer** (`app/api/`)
- REST endpoints using FastAPI
- Authentication & authorization
- Request validation with Pydantic

#### 2. **Service Layer** (`app/services/`)
- Business logic and orchestration
- LLM interactions via LangChain
- Integration with external APIs (Google, GitHub, etc.)

#### 3. **Models** (`app/models/`)
- SQLAlchemy ORM models
- Database schema definitions
- Relationships and constraints

#### 4. **Tasks** (`app/tasks/`)
- Asynchronous background jobs
- Scheduled tasks with Celery Beat
- Email notifications and cleanup jobs

#### 5. **Agent Types**
- **Research Agent**: Web search and fact-checking
- **Docs Agent**: Google Docs creation and editing
- **Sheets Agent**: Google Sheets with formulas, pivot tables, formatting
- **Slides Agent**: Google Slides presentation generation
- **Scheduler Agent**: Meeting scheduling and calendar management

---

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

Follow the existing code structure and conventions:

- Use **type hints** for all function parameters and return values
- Add **docstrings** for public functions
- Follow **PEP 8** style guidelines
- Keep functions **small and focused** (single responsibility)

### 3. Add Tests

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=app tests/
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: Add your feature description"

# Commit message format:
# feat: New feature
# fix: Bug fix
# docs: Documentation update
# refactor: Code refactoring
# test: Add tests
# chore: Maintenance tasks
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

---

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_agents.py

# With coverage report
pytest --cov=app --cov-report=html

# Watch mode (re-run on file changes)
pytest-watch
```

### Test Structure

```python
# tests/test_agents.py
import pytest
from app.services.agent_service import AgentService

@pytest.fixture
def agent_service():
    return AgentService()

def test_create_agent(agent_service):
    agent = agent_service.create_agent(
        name="Test Agent",
        type="research"
    )
    assert agent.name == "Test Agent"
    assert agent.type == "research"
```

### Writing Tests

1. **Unit Tests**: Test individual functions in isolation
2. **Integration Tests**: Test API endpoints with database
3. **E2E Tests**: Test complete user workflows

---

## Common Tasks

### Adding a New API Endpoint

1. **Define schema** (`app/schemas/`):

```python
# app/schemas/agent.py
from pydantic import BaseModel

class AgentCreate(BaseModel):
    name: str
    type: str
    config: dict = {}
```

2. **Create route** (`app/api/`):

```python
# app/api/agents.py
from fastapi import APIRouter, Depends
from app.schemas.agent import AgentCreate

router = APIRouter()

@router.post("/agents")
def create_agent(agent: AgentCreate):
    # Implementation
    pass
```

3. **Register route** (`app/main.py`):

```python
from app.api import agents

app.include_router(agents.router, prefix="/api", tags=["agents"])
```

### Adding a Database Migration

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Review migration file in alembic/versions/

# Apply migration
alembic upgrade head

# Rollback (if needed)
alembic downgrade -1
```

### Adding a Celery Task

```python
# app/tasks/my_tasks.py
from app.celery_app import celery

@celery.task(name="my_tasks.process_data")
def process_data(data: dict):
    # Your background task logic
    return {"status": "completed"}
```

**Schedule task** (Celery Beat):

```python
# app/celery_app.py
from celery.schedules import crontab

celery.conf.beat_schedule = {
    'process-data-daily': {
        'task': 'my_tasks.process_data',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
}
```

### Adding a New Agent Type

1. **Create agent class** (`app/services/`):

```python
# app/services/my_new_agent.py
from langchain.chains import LLMChain
from app.services.llm_service import get_llm

class MyNewAgent:
    def __init__(self, model: str = "gpt-4"):
        self.llm = get_llm(model)
    
    def execute(self, task: str) -> dict:
        # Agent logic
        return {"result": "Success"}
```

2. **Register in service** (`app/services/agent_service.py`):

```python
from app.services.my_new_agent import MyNewAgent

AGENT_TYPES = {
    "research": ResearchAgent,
    "docs": GoogleDocsAgent,
    "my_new_agent": MyNewAgent,  # Add here
}
```

### Integrating a New LLM Provider

1. **Add API key to `.env`**:

```bash
NEW_PROVIDER_API_KEY=your-api-key
```

2. **Update LLM service** (`app/services/llm_service.py`):

```python
from langchain_community.llms import NewProvider

def get_llm(model: str):
    if model.startswith("new-provider/"):
        return NewProvider(api_key=settings.NEW_PROVIDER_API_KEY)
    # ... existing providers
```

3. **Update budget tracking** (`app/services/budget_service.py`):

```python
MODEL_COSTS = {
    "new-provider/model-name": {
        "input": 0.001,  # per 1K tokens
        "output": 0.002,
    },
    # ... existing models
}
```

---

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# View logs
docker logs agenthq-postgres

# Reset database (CAUTION: destroys data)
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping
# Should return: PONG

# View Redis keys
redis-cli keys '*'
```

### Celery Worker Not Processing Tasks

```bash
# Check worker status
celery -A app.celery_app inspect active

# Purge all tasks (CAUTION)
celery -A app.celery_app purge

# Restart worker
pkill -f 'celery worker'
celery -A app.celery_app worker --loglevel=info
```

### Google API Errors

- **403 Forbidden**: Check OAuth scopes in Google Cloud Console
- **401 Unauthorized**: Refresh OAuth token or re-authenticate
- **429 Rate Limited**: Implement backoff and retry logic

### LLM API Errors

- **401 Invalid API Key**: Check `.env` file for correct key
- **429 Rate Limit**: Use exponential backoff
- **500 Server Error**: Check provider status page

---

## Resources

### Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Celery Docs](https://docs.celeryproject.org/)
- [LangChain Docs](https://python.langchain.com/)
- [Google APIs](https://developers.google.com/docs/api)

### Internal Docs

- [Claude Integration](./CLAUDE_INTEGRATION.md)
- [Enhanced OAuth](./ENHANCED_OAUTH.md)
- [Sheets Advanced Features](./SHEETS_ADVANCED_FEATURES.md)
- [Budget Tracking](./BUDGET_TRACKING.md)
- [API Documentation](./API_DOCUMENTATION.md)

### Code Style

- [PEP 8](https://pep8.org/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

### Useful Commands

```bash
# Format code
black app/

# Lint code
flake8 app/

# Type checking
mypy app/

# Generate requirements
pip freeze > requirements.txt

# Database backup
pg_dump -U user agenthq > backup.sql

# Restore database
psql -U user agenthq < backup.sql
```

---

## Next Steps

1. **Explore the codebase**: Start with `app/main.py` and follow the imports
2. **Run the test suite**: Understand how components are tested
3. **Pick a good first issue**: Look for issues labeled "good first issue"
4. **Ask questions**: Don't hesitate to reach out to the team

**Welcome aboard! Happy coding! 🚀**
