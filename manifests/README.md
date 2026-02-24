# AgentHQ FactoryHub Integration Manifests

This directory contains service manifests for integrating AgentHQ with FactoryHub.

## Files

### `ai-agent.json`
FactoryHub service manifest for AgentHQ. This JSON file describes:

- **Service metadata**: name, version, description, tags
- **Runtime configuration**: Docker Compose setup
- **API endpoints**: OpenAPI spec, health checks, FactoryHub callbacks
- **Authentication**: JWT + Google OAuth 2.0 flow
- **Capabilities**: Available agents (Docs, Sheets, Slides, Orchestrator)
- **Dependencies**: PostgreSQL (pgvector), Redis, external APIs
- **Environment variables**: Required configuration
- **Resource limits**: CPU, memory, storage requirements
- **Monitoring**: Health checks, metrics, logging
- **Scaling**: Horizontal scaling configuration
- **Event integration**: Incoming/outgoing events for FactoryHub

## Usage

### For FactoryHub Integration

1. **Deploy AgentHQ** using Docker Compose:
   ```bash
   docker-compose up -d
   ```

2. **Register with FactoryHub**:
   ```bash
   factoryhub service register \
     --manifest manifests/ai-agent.json \
     --endpoint http://localhost:8000
   ```

3. **Configure webhook** (optional):
   ```bash
   export FACTORYHUB_WEBHOOK_URL="https://factoryhub.example.com/webhooks/agenthq"
   export FACTORYHUB_TOKEN="your-secret-token"
   ```

### Event Flow

**Incoming Events** (from FactoryHub → AgentHQ):
- `task.create` — Create a new AI task
- `task.cancel` — Cancel a running task

**Outgoing Events** (from AgentHQ → FactoryHub):
- `task.completed` — Task finished successfully
- `task.failed` — Task execution failed
- `task.progress` — Real-time progress updates

## Environment Variables

Required for FactoryHub integration:

```bash
# Core
DATABASE_URL="postgresql://user:pass@localhost:5432/agenthq"
REDIS_URL="redis://localhost:6379/0"

# AI
ANTHROPIC_API_KEY="sk-ant-..."

# Google OAuth
GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="GOCSPX-..."

# Security
JWT_SECRET="your-random-secret-key"

# FactoryHub (optional)
FACTORYHUB_TOKEN="your-factoryhub-token"
FACTORYHUB_WEBHOOK_URL="https://factoryhub.example.com/webhooks/agenthq"
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### OpenAPI Spec
```bash
curl http://localhost:8000/openapi.json
```

### FactoryHub Callback
```bash
curl -X POST http://localhost:8000/api/v1/factoryhub/callback \
  -H "X-FactoryHub-Token: your-token" \
  -H "Content-Type: application/json" \
  -d '{"event": "task.create", "data": {...}}'
```

## Next Steps

After creating the manifest:

1. ✅ Manifest created (`manifests/ai-agent.json`)
2. ⏳ Implement FactoryHub API endpoints (`backend/app/api/v1/factoryhub.py`)
3. ⏳ Add webhook delivery logic
4. ⏳ Test integration with FactoryHub Go backend

See `TASKS.md` for detailed implementation checklist.
