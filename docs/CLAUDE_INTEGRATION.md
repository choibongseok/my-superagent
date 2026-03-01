# Claude/Anthropic Integration

> **Sprint 6 Feature** — Completed 2026-03-01  
> **Status**: ✅ Ready for production

---

## 📋 Overview

AgentHQ now supports **Anthropic's Claude models** alongside OpenAI's GPT models. Users can select which LLM provider and specific model to use for each task, enabling:

- **Cost optimization**: Choose cheaper models for simple tasks
- **Quality control**: Use Claude Opus for complex reasoning, Haiku for speed
- **Vendor flexibility**: Avoid vendor lock-in
- **Compliance**: Meet data residency or provider requirements

---

## 🚀 Features

### Supported Models

#### **OpenAI (Default)**
- `gpt-4-turbo-preview` (default) — Best for complex tasks
- `gpt-4` — Standard GPT-4
- `gpt-3.5-turbo` — Fast and cost-effective

#### **Anthropic Claude**
- `claude-3-opus-20240229` — Highest capability, best for complex tasks
- `claude-3-sonnet-20240229` — Balanced performance and speed
- `claude-3-haiku-20240307` — Fastest and most cost-effective

### LLM Selection Per Task

Each task now stores:
- **llm_provider**: `"openai"` or `"anthropic"`
- **llm_model**: Specific model name

This allows:
- Per-task model selection
- Cost analytics by model
- Budget tracking by provider
- Performance comparisons

---

## 🔧 Implementation

### 1. Database Changes

**Migration**: `006_claude_integration.py`

```sql
-- Add LLM configuration to tasks table
ALTER TABLE tasks ADD COLUMN llm_provider VARCHAR(50) NOT NULL DEFAULT 'openai';
ALTER TABLE tasks ADD COLUMN llm_model VARCHAR(100) NOT NULL DEFAULT 'gpt-4-turbo-preview';
CREATE INDEX ix_tasks_llm_provider ON tasks(llm_provider);
```

**Run migration**:
```bash
cd backend
alembic upgrade head
```

### 2. API Changes

**TaskCreate Schema** (`app/schemas/task.py`):

```python
class TaskCreate(BaseModel):
    prompt: str
    task_type: TaskType
    metadata: Optional[Dict[str, Any]] = None
    
    # NEW: LLM selection
    llm_provider: str = Field(default="openai", pattern="^(openai|anthropic)$")
    llm_model: str = Field(
        default="gpt-4-turbo-preview",
        description="Model name (e.g., gpt-4-turbo-preview, claude-3-opus-20240229)"
    )
```

**Example API Request**:

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Research quantum computing trends",
    "task_type": "research",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-opus-20240229"
  }'
```

### 3. Agent Updates

**BaseAgent** (`app/agents/base.py`):

The base agent already supports both providers via the `_create_llm` method:

```python
def _create_llm(self, provider: str, model: str, temperature: float, max_tokens: int):
    callbacks = [self.langfuse_handler] if self.langfuse_handler else None
    
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            callbacks=callbacks,
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            callbacks=callbacks,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
```

**All agents** (Research, Docs, Sheets, Slides) inherit this functionality automatically.

### 4. Celery Tasks

Updated all task processors to accept and use `llm_provider` and `llm_model`:

```python
@celery_app.task(name="agents.process_research_task", bind=True, max_retries=3)
def process_research_task(
    self,
    task_id: str,
    prompt: str,
    user_id: str,
    llm_provider: str = "openai",
    llm_model: str = "gpt-4-turbo-preview",
):
    agent = ResearchAgent(
        user_id=user_id,
        session_id=task_id,
        llm_provider=llm_provider,
        model=llm_model,
    )
    # ...
```

---

## 📚 Usage Examples

### Research Task with Claude Opus

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Research the latest advancements in quantum computing and their implications for cryptography",
    "task_type": "research",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-opus-20240229"
  }'
```

### Docs Task with Claude Sonnet (Balanced)

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a comprehensive business proposal for a SaaS startup",
    "task_type": "docs",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-sonnet-20240229",
    "metadata": {
      "title": "SaaS Business Proposal"
    }
  }'
```

### Sheets Task with Claude Haiku (Fast & Cheap)

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Generate a simple sales tracking spreadsheet for Q1 2024",
    "task_type": "sheets",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-haiku-20240307",
    "metadata": {
      "title": "Q1 Sales Tracker"
    }
  }'
```

### Default (OpenAI GPT-4)

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Research AI ethics frameworks",
    "task_type": "research"
  }'
```

**Note**: If `llm_provider` and `llm_model` are omitted, defaults to `openai`/`gpt-4-turbo-preview`.

---

## 🔍 Monitoring & Analytics

### LangFuse Integration

All LLM calls (both OpenAI and Anthropic) are automatically tracked in LangFuse with:

- **Provider metadata**: `llm_provider`, `llm_model`
- **Cost tracking**: Per-provider cost breakdown
- **Performance metrics**: Latency, token usage
- **Quality metrics**: Success rates, error rates

**LangFuse Dashboard**: https://cloud.langfuse.com

### Budget Tracking

The existing Budget Tracking system (Sprint 5) automatically tracks costs per provider:

```bash
# Get cost analytics by provider
GET /api/v1/budget/costs/summary

# Response
{
  "total_cost": 45.23,
  "by_provider": {
    "openai": 30.15,
    "anthropic": 15.08
  },
  "by_model": {
    "gpt-4-turbo-preview": 25.50,
    "gpt-3.5-turbo": 4.65,
    "claude-3-opus-20240229": 10.20,
    "claude-3-sonnet-20240229": 4.88
  }
}
```

---

## ⚙️ Configuration

### Environment Variables

Add to `backend/.env`:

```bash
# OpenAI (existing)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo-preview

# Anthropic (new)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229
```

**Obtain Anthropic API Key**: https://console.anthropic.com/

### Model Defaults

Configured in `app/core/config.py`:

```python
class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    
    # Anthropic
    ANTHROPIC_API_KEY: str = Field(default="")
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"
```

---

## 🧪 Testing

### Run Integration Tests

```bash
cd backend
python test_claude_integration.py
```

**Test Coverage**:
- ✅ API schema validation
- ✅ Task creation with Claude models
- ✅ All agent types (Research, Docs, Sheets, Slides)
- ✅ Database field persistence
- ✅ Celery task execution
- ✅ LangFuse tracing

### Manual Testing

1. **Start services**:
   ```bash
   docker-compose up -d
   ```

2. **Create test task**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/tasks \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "Test Claude integration",
       "task_type": "research",
       "llm_provider": "anthropic",
       "llm_model": "claude-3-haiku-20240307"
     }'
   ```

3. **Check task status**:
   ```bash
   curl http://localhost:8000/api/v1/tasks/{task_id}
   ```

4. **Verify in database**:
   ```sql
   SELECT id, prompt, llm_provider, llm_model, status 
   FROM tasks 
   WHERE llm_provider = 'anthropic';
   ```

---

## 📊 Model Comparison

| Model | Provider | Speed | Cost | Best For |
|-------|----------|-------|------|----------|
| **claude-3-opus** | Anthropic | ⭐⭐ | 💰💰💰 | Complex reasoning, code, research |
| **claude-3-sonnet** | Anthropic | ⭐⭐⭐ | 💰💰 | Balanced tasks, general use |
| **claude-3-haiku** | Anthropic | ⭐⭐⭐⭐⭐ | 💰 | Fast responses, simple tasks |
| **gpt-4-turbo** | OpenAI | ⭐⭐⭐ | 💰💰💰 | Complex tasks, coding |
| **gpt-3.5-turbo** | OpenAI | ⭐⭐⭐⭐ | 💰 | Simple tasks, speed |

**Cost Reference** (as of 2024):
- Claude Opus: $15/M input, $75/M output
- Claude Sonnet: $3/M input, $15/M output
- Claude Haiku: $0.25/M input, $1.25/M output
- GPT-4 Turbo: $10/M input, $30/M output
- GPT-3.5 Turbo: $0.50/M input, $1.50/M output

---

## 🔐 Security & Best Practices

### API Key Management

✅ **DO**:
- Store API keys in `.env` (never commit)
- Use environment variables in production
- Rotate keys periodically
- Monitor usage for anomalies

❌ **DON'T**:
- Hard-code API keys in source code
- Commit `.env` files to git
- Share keys in chat/email
- Use the same key across environments

### Cost Control

1. **Set budget alerts** (Sprint 5):
   ```bash
   POST /api/v1/budget
   {
     "limit": 100.00,
     "period": "monthly",
     "alert_threshold": 0.75
   }
   ```

2. **Use cheaper models for simple tasks**:
   - Research summaries → Haiku or GPT-3.5
   - Complex analysis → Opus or GPT-4

3. **Monitor usage in LangFuse**:
   - Daily cost reports
   - Per-model breakdowns
   - Anomaly detection

---

## 🚧 Troubleshooting

### "Anthropic API key not set"

**Solution**:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
# Or add to backend/.env
```

### "Unsupported LLM provider: anthropic"

**Solution**: Install `langchain-anthropic`:
```bash
cd backend
pip install langchain-anthropic
```

### Migration fails

**Solution**: Run Docker services first:
```bash
docker-compose up -d postgres
sleep 5
alembic upgrade head
```

### Claude responses are slow

**Solution**: Use a faster model:
- Replace `claude-3-opus` → `claude-3-sonnet`
- Or use `claude-3-haiku` for speed-critical tasks

---

## 📝 Next Steps

### Completed ✅
- [x] Database schema for LLM configuration
- [x] API endpoints accept llm_provider and llm_model
- [x] All agents support Claude models
- [x] Celery tasks pass model parameters
- [x] Migration created and documented
- [x] Testing script provided

### Future Enhancements
- [ ] **Model auto-selection**: AI chooses best model for task
- [ ] **Streaming responses**: Real-time token streaming
- [ ] **Model fallback**: Auto-retry with different model on failure
- [ ] **UI model picker**: Dropdown in frontend
- [ ] **Cost estimation**: Pre-task cost prediction
- [ ] **A/B testing**: Compare model outputs

---

## 📚 Related Documentation

- **Architecture**: [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- **LangChain Guide**: [docs/LANGCHAIN_GUIDE.md](LANGCHAIN_GUIDE.md)
- **LangFuse Setup**: [docs/LANGFUSE_SETUP.md](LANGFUSE_SETUP.md)
- **Budget Tracking**: [docs/sprint5-budget-tracking-completion.md](sprint5-budget-tracking-completion.md)
- **API Reference**: http://localhost:8000/docs

---

## 🤝 Contributing

Found a bug or want to add support for more models? See [CONTRIBUTING.md](../CONTRIBUTING.md).

**Popular requests**:
- Google PaLM/Gemini support
- Cohere models
- Local LLMs (Llama, Mistral via Ollama)
- Azure OpenAI integration

---

**Created**: 2026-03-01  
**Author**: AgentHQ Team  
**Sprint**: 6  
**Status**: ✅ Production Ready
