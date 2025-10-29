# 🏗️ AgentHQ Architecture

> Multi-Client AI Super Agent Hub System Design

---

## Overview

AgentHQ is a cross-platform intelligent agent system that integrates with Google Workspace to create documents, spreadsheets, and presentations through natural language commands.

### Design Principles

1. **Multi-Client**: Single backend serves desktop (Tauri) and mobile (Flutter) clients
2. **Cloud-Native**: Designed for Google Cloud Run deployment
3. **Async-First**: Non-blocking operations for scalability
4. **API-Driven**: RESTful API with clear separation of concerns
5. **Secure by Default**: OAuth 2.0, JWT tokens, HTTPS everywhere

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
├──────────────────────┬──────────────────────┬───────────────────┤
│   Desktop (Tauri)    │   Mobile (Flutter)   │   Future: Web     │
│   • React UI         │   • Dart UI          │   • React/Vue     │
│   • Native OS        │   • iOS/Android      │   • Browser       │
│   • OAuth Flow       │   • OAuth Flow       │   • PWA           │
└──────────┬───────────┴──────────┬───────────┴───────────────────┘
           │                      │
           └──────────┬───────────┘
                      │ HTTPS/REST
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway                              │
│                    FastAPI (Python 3.11+)                        │
├─────────────────────────────────────────────────────────────────┤
│  • Authentication (JWT + OAuth)                                  │
│  • Rate Limiting                                                 │
│  • Request Validation                                            │
│  • API Documentation (OpenAPI)                                   │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ├─────────────────┬─────────────────┬──────────────────┐
           ▼                 ▼                 ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌─────────────┐ ┌──────────┐
│  Task Queue      │ │  Database    │ │   Cache     │ │  LLM     │
│  Celery + Redis  │ │  PostgreSQL  │ │   Redis     │ │ Provider │
│                  │ │  + PGVector  │ │             │ │          │
└────────┬─────────┘ └──────────────┘ └─────────────┘ └──────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Workers                               │
│                   Celery Workers (Async)                         │
├─────────────────────────────────────────────────────────────────┤
│  • Research Agent (Web Scraping + Analysis)                      │
│  • Docs Agent (Google Docs API)                                  │
│  • Sheets Agent (Google Sheets API)                              │
│  • Slides Agent (Google Slides API)                              │
│  • Memory Manager (Vector Storage)                               │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                             │
├────────────────┬────────────────┬───────────────┬───────────────┤
│  Google Docs   │ Google Sheets  │ Google Slides │ Google Drive  │
└────────────────┴────────────────┴───────────────┴───────────────┘
```

---

## Component Details

### 1. Client Layer

#### Desktop (Tauri + React)
- **Purpose**: Primary desktop application
- **Tech Stack**: 
  - Tauri 1.5+ (Rust backend)
  - React 18 + TypeScript
  - Tailwind CSS + shadcn/ui
- **Features**:
  - Native OS integration
  - Local storage
  - System tray
  - Keyboard shortcuts
  - Native notifications

#### Mobile (Flutter)
- **Purpose**: Mobile extension client
- **Tech Stack**:
  - Flutter 3.16+
  - Riverpod/Bloc state management
  - google_sign_in plugin
- **Features**:
  - Cross-platform (iOS/Android)
  - Push notifications
  - Offline mode
  - Biometric auth

---

### 2. API Gateway (FastAPI)

#### Responsibilities
- Request routing and validation
- Authentication and authorization
- Rate limiting and throttling
- API documentation
- Error handling
- CORS configuration

#### Key Endpoints

```
Authentication:
  GET  /api/v1/auth/google        - Initiate OAuth
  POST /api/v1/auth/callback      - OAuth callback
  POST /api/v1/auth/refresh       - Refresh tokens

Tasks:
  POST   /api/v1/tasks            - Create task
  GET    /api/v1/tasks            - List tasks
  GET    /api/v1/tasks/{id}       - Get task
  DELETE /api/v1/tasks/{id}       - Cancel task

Memory:
  GET    /api/v1/memory           - Get memories
  POST   /api/v1/memory           - Save memory
  DELETE /api/v1/memory/{id}      - Delete memory

Health:
  GET    /api/v1/ping             - Health check
  GET    /api/v1/status           - Service status
```

#### Authentication Flow

```
1. Client → GET /auth/google
   ↓ Returns auth URL
   
2. User authorizes in browser
   ↓ Redirects with code
   
3. Client → POST /auth/callback {code}
   ↓ Exchanges code for tokens
   
4. Backend validates with Google
   ↓ Creates/updates user
   
5. Backend → {access_token, refresh_token}
   ↓
   
6. Client stores tokens
   ↓
   
7. Client → API with Authorization: Bearer {token}
```

---

### 3. Database Layer

#### PostgreSQL + PGVector

**Purpose**: Primary data store with vector search capabilities

**Tables**:

```sql
-- Users
users (
  id UUID PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  full_name VARCHAR(255),
  google_id VARCHAR(255) UNIQUE,
  google_access_token VARCHAR(512),
  google_refresh_token VARCHAR(512),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Tasks
tasks (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  prompt TEXT NOT NULL,
  task_type VARCHAR(50) NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  result JSONB,
  error_message TEXT,
  document_url VARCHAR(512),
  document_id VARCHAR(255),
  metadata JSONB,
  celery_task_id VARCHAR(255),
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Memories (for conversation context)
memories (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  task_id UUID REFERENCES tasks(id),
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  metadata JSONB,
  created_at TIMESTAMP
)
```

---

### 4. Task Queue (Celery + Redis)

#### Purpose
- Asynchronous task processing
- Background job execution
- Task scheduling and retry logic

#### Task Types

```python
# Research Task
@celery.task
def research_task(prompt: str, user_id: str) -> dict:
    """Perform web research and analysis."""
    pass

# Document Generation
@celery.task
def create_document(prompt: str, research_data: dict, user_id: str) -> str:
    """Create Google Doc with research results."""
    pass

# Spreadsheet Generation
@celery.task
def create_spreadsheet(prompt: str, data: list, user_id: str) -> str:
    """Create Google Sheet with structured data."""
    pass

# Presentation Generation
@celery.task
def create_slides(prompt: str, content: dict, user_id: str) -> str:
    """Create Google Slides presentation."""
    pass
```

#### Task Lifecycle

```
1. Client creates task
   ↓
2. API creates task record (status: pending)
   ↓
3. API queues Celery task
   ↓
4. Celery worker picks up task
   ↓
5. Worker updates status (status: processing)
   ↓
6. Worker executes agent logic
   ↓
7. Worker updates result (status: completed/failed)
   ↓
8. Client polls for result
```

---

### 5. Agent Workers

#### Research Agent
- Web scraping (Playwright)
- Content extraction (BeautifulSoup)
- Information synthesis (LLM)
- Source citation

#### Document Agent
- Google Docs API integration
- Markdown to Docs formatting
- Style and formatting
- Section organization

#### Spreadsheet Agent
- Data structuring
- Google Sheets API
- Chart generation
- Formula creation

#### Presentation Agent
- Slide layout design
- Content distribution
- Image integration
- Google Slides API

#### Memory Manager
- Vector embeddings (OpenAI)
- Semantic search (PGVector)
- Context retrieval
- Conversation history

---

### 6. External Services

#### LLM Providers
- **OpenAI GPT-4**: Primary reasoning
- **Anthropic Claude**: Alternative/backup

#### Google Workspace APIs
- **Google Docs API**: Document creation
- **Google Sheets API**: Spreadsheet creation
- **Google Slides API**: Presentation creation
- **Google Drive API**: File management

---

## Data Flow Examples

### Example 1: Create Document

```
1. User (Desktop) → "Create a report on AI trends"
   ↓
2. Desktop → POST /api/v1/tasks
   {
     "prompt": "Create a report on AI trends",
     "task_type": "docs"
   }
   ↓
3. API Gateway validates request, creates task
   ↓
4. Task queued to Celery (task_id: abc-123)
   ↓
5. Desktop → GET /api/v1/tasks/abc-123 (polling)
   ↓
6. Celery Worker:
   a. Research Agent scrapes web
   b. LLM analyzes and synthesizes
   c. Document Agent creates Google Doc
   d. Updates task with doc URL
   ↓
7. Desktop receives completed task with document_url
   ↓
8. User opens Google Doc in browser
```

### Example 2: Multi-Platform Sync

```
1. User creates task on Desktop
   ↓
2. Task stored in database
   ↓
3. User opens Mobile app
   ↓
4. Mobile → GET /api/v1/tasks
   ↓
5. Mobile receives all tasks (including from Desktop)
   ↓
6. User can view results on Mobile
```

---

## Security Architecture

### Authentication Layers

```
Layer 1: Google OAuth 2.0
  - User identity verification
  - Google Workspace permissions
  - Token refresh mechanism

Layer 2: JWT Tokens
  - Access token (30 min expiry)
  - Refresh token (7 day expiry)
  - Token rotation

Layer 3: API Authorization
  - Bearer token validation
  - User-resource ownership
  - Rate limiting per user
```

### Data Protection

1. **In Transit**: HTTPS/TLS 1.3
2. **At Rest**: Database encryption
3. **Tokens**: Encrypted storage
4. **Secrets**: Environment variables, never in code

---

## Scalability Considerations

### Horizontal Scaling

```
┌─────────────────────────────────────────────┐
│          Load Balancer (Cloud LB)           │
└──────────────┬──────────────────────────────┘
               │
       ┌───────┼───────┐
       ▼       ▼       ▼
   ┌─────┐ ┌─────┐ ┌─────┐
   │ API │ │ API │ │ API │  ← Auto-scaling
   │  1  │ │  2  │ │  N  │
   └─────┘ └─────┘ └─────┘
       │       │       │
       └───────┼───────┘
               ▼
         ┌──────────┐
         │ Database │  ← Connection pooling
         └──────────┘
```

### Performance Optimizations

1. **Caching**:
   - Redis for session data
   - API response caching
   - Document template caching

2. **Database**:
   - Connection pooling
   - Read replicas
   - Query optimization
   - Indexing strategy

3. **Async Processing**:
   - Non-blocking I/O
   - Celery workers scaling
   - Task priority queues

---

## Deployment Architecture

### Development

```
localhost:8000   → FastAPI
localhost:5432   → PostgreSQL
localhost:6379   → Redis
localhost:5555   → Celery Flower
```

### Production (Google Cloud)

```
Cloud Run        → API Gateway (auto-scaling)
Cloud SQL        → PostgreSQL (managed)
Memorystore      → Redis (managed)
Cloud Storage    → File artifacts
Cloud CDN        → Static assets
Cloud Armor      → DDoS protection
```

---

## Monitoring & Observability

### Metrics
- Request rate, latency, errors
- Task queue length
- Worker utilization
- Database connections
- Cache hit rate

### Logging
- Structured JSON logs
- Log levels (DEBUG, INFO, ERROR)
- Correlation IDs
- Request tracing

### Alerting
- API downtime
- Task failures
- Database issues
- Rate limit exceeded

---

## Future Enhancements

### Phase 1 (Current)
- ✅ Basic architecture
- ✅ OAuth integration
- ✅ Task queue
- ✅ Database models

### Phase 2
- [ ] Agent implementation
- [ ] Google Workspace integration
- [ ] Memory/context system
- [ ] Web research

### Phase 3
- [ ] WebSocket for real-time updates
- [ ] Team collaboration
- [ ] Advanced analytics
- [ ] Template marketplace

### Phase 4
- [ ] Multi-tenant support
- [ ] Enterprise features
- [ ] Advanced AI capabilities
- [ ] Plugin system

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Google Workspace APIs](https://developers.google.com/workspace)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

**Last Updated**: 2024-10-29
