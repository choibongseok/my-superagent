# 🏗️ AgentHQ Architecture Documentation

> **Last Updated**: 2026-03-01  
> **Version**: Sprint 8 (Complete Feature Set)

---

## 📑 Table of Contents

1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [Agent Architecture](#agent-architecture)
4. [Data Flow](#data-flow)
5. [Authentication Flow](#authentication-flow)
6. [Mobile Architecture](#mobile-architecture)
7. [Database Schema](#database-schema)
8. [Technology Stack](#technology-stack)

---

## System Overview

AgentHQ is a multi-platform AI automation system built with a microservices-inspired architecture.

```mermaid
graph TB
    subgraph "Client Layer"
        Web[Web Client<br/>React/Next.js]
        Desktop[Desktop App<br/>Tauri]
        Mobile[Mobile App<br/>Flutter]
    end

    subgraph "API Layer"
        FastAPI[FastAPI Backend<br/>REST API]
        WebSocket[WebSocket<br/>Real-time Updates]
    end

    subgraph "Processing Layer"
        Celery[Celery Workers<br/>Async Tasks]
        Beat[Celery Beat<br/>Scheduler]
        Agents[Agent Pool<br/>LangChain Agents]
    end

    subgraph "Storage Layer"
        Postgres[(PostgreSQL<br/>Main DB + PGVector)]
        Redis[(Redis<br/>Cache + Queue)]
    end

    subgraph "External Services"
        OpenAI[OpenAI API<br/>GPT-4]
        Claude[Anthropic API<br/>Claude 3]
        Google[Google Workspace<br/>Docs/Sheets/Slides]
        LangFuse[LangFuse<br/>Observability]
    end

    Web --> FastAPI
    Desktop --> FastAPI
    Mobile --> FastAPI
    FastAPI --> WebSocket
    FastAPI --> Celery
    Celery --> Beat
    Celery --> Agents
    Agents --> OpenAI
    Agents --> Claude
    Agents --> Google
    Agents --> LangFuse
    FastAPI --> Postgres
    FastAPI --> Redis
    Celery --> Postgres
    Celery --> Redis
```

### Key Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **FastAPI Backend** | Python 3.11+ | REST API, request handling |
| **Celery Workers** | Celery 5.3+ | Asynchronous task processing |
| **PostgreSQL** | PostgreSQL 15+ | Primary data store + vector search |
| **Redis** | Redis 7+ | Task queue, caching, pub/sub |
| **LangChain** | LangChain 0.1+ | Agent orchestration framework |
| **LangFuse** | LangFuse 2.6+ | LLM observability & tracing |

---

## Backend Architecture

### FastAPI Application Structure

```mermaid
graph LR
    subgraph "FastAPI App"
        Main[main.py<br/>Application Entry]
        
        subgraph "API Layer"
            Auth[auth.py<br/>Authentication]
            Agents[agents.py<br/>Agent Management]
            Convos[conversations.py<br/>Chat Management]
            Tasks[tasks.py<br/>Task Status]
            OAuth[oauth.py<br/>OAuth Flow]
        end
        
        subgraph "Service Layer"
            AgentSvc[AgentService<br/>Agent Logic]
            AuthSvc[AuthService<br/>Token Management]
            ConvoSvc[ConversationService<br/>Memory Management]
            BudgetSvc[BudgetService<br/>Cost Tracking]
            FactCheck[FactCheckService<br/>Citation Validation]
        end
        
        subgraph "Data Layer"
            Models[SQLAlchemy Models<br/>ORM Entities]
            Schemas[Pydantic Schemas<br/>Validation]
        end
        
        Main --> API
        API --> Service
        Service --> Data
    end
```

### Directory Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── database.py             # DB connection
│   ├── api/                    # API endpoints
│   │   ├── v1/
│   │   │   ├── auth.py         # /api/v1/auth/*
│   │   │   ├── agents.py       # /api/v1/agents/*
│   │   │   ├── conversations.py # /api/v1/conversations/*
│   │   │   ├── tasks.py        # /api/v1/tasks/*
│   │   │   ├── oauth.py        # /api/v1/oauth/*
│   │   │   └── budget.py       # /api/v1/budget/*
│   ├── agents/                 # Agent implementations
│   │   ├── base_agent.py       # BaseAgent class
│   │   ├── research_agent.py   # Research Agent
│   │   ├── docs_agent.py       # Google Docs Agent
│   │   ├── sheets_agent.py     # Google Sheets Agent
│   │   └── slides_agent.py     # Google Slides Agent
│   ├── services/               # Business logic
│   │   ├── agent_service.py
│   │   ├── auth_service.py
│   │   ├── conversation_service.py
│   │   ├── budget_service.py
│   │   └── fact_check_service.py
│   ├── tasks/                  # Celery tasks
│   │   ├── agent_tasks.py      # Agent execution
│   │   ├── oauth_tasks.py      # Token rotation
│   │   └── budget_tasks.py     # Budget monitoring
│   ├── models/                 # Database models
│   │   ├── user.py
│   │   ├── agent.py
│   │   ├── conversation.py
│   │   ├── task.py
│   │   └── oauth.py
│   ├── schemas/                # Pydantic schemas
│   ├── core/                   # Core utilities
│   │   ├── config.py           # Settings
│   │   ├── security.py         # Auth helpers
│   │   ├── langfuse_config.py  # LangFuse setup
│   │   └── encryption.py       # Token encryption
│   ├── memory/                 # Memory management
│   │   ├── memory_manager.py   # Unified memory
│   │   ├── conversation_memory.py
│   │   └── vector_memory.py
│   ├── tools/                  # Agent tools
│   │   ├── google_tools.py     # Workspace tools
│   │   ├── search_tools.py     # Web search
│   │   └── weather_tools.py    # Weather API
│   └── prompts/                # Agent prompts
│       ├── research_prompts.py
│       ├── docs_prompts.py
│       ├── sheets_prompts.py
│       └── slides_prompts.py
```

---

## Agent Architecture

### Agent Orchestration Flow

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI
    participant Celery as Celery Worker
    participant Agent as LangChain Agent
    participant LLM as OpenAI/Claude
    participant Tools as Agent Tools
    participant GWS as Google Workspace
    participant LangFuse as LangFuse

    User->>API: POST /api/v1/agents/execute
    API->>API: Validate request
    API->>Celery: Queue agent_task
    API-->>User: 202 Accepted (task_id)
    
    Celery->>Agent: Initialize agent
    Agent->>LangFuse: Start trace
    Agent->>LLM: Send prompt + context
    
    loop Agent Reasoning
        LLM->>Agent: Tool call decision
        Agent->>Tools: Execute tool
        Tools->>GWS: API request
        GWS-->>Tools: API response
        Tools-->>Agent: Tool result
        Agent->>LLM: Send result
        Agent->>LangFuse: Log interaction
    end
    
    LLM-->>Agent: Final answer
    Agent->>Celery: Update task status
    Agent->>LangFuse: End trace
    Celery-->>User: Notify completion (WebSocket)
```

### Agent Types & Capabilities

```mermaid
graph TD
    BaseAgent[BaseAgent<br/>LangChain Framework]
    
    BaseAgent --> Research[ResearchAgent<br/>Web Search & Analysis]
    BaseAgent --> Docs[DocsAgent<br/>Document Generation]
    BaseAgent --> Sheets[SheetsAgent<br/>Data & Analytics]
    BaseAgent --> Slides[SlidesAgent<br/>Presentations]
    
    Research --> SearchTool[Web Search Tool]
    Research --> WeatherTool[Weather Tool]
    Research --> CiteTool[Citation Tool]
    
    Docs --> DocsTool[Google Docs API]
    Docs --> CiteTool
    Docs --> StyleTool[Document Styling]
    
    Sheets --> SheetsTool[Google Sheets API]
    Sheets --> ChartTool[Chart Generation]
    Sheets --> FormulaTool[Formula Tools]
    Sheets --> FormatTool[Cell Formatting]
    Sheets --> PivotTool[Pivot Tables]
    Sheets --> ValidationTool[Data Validation]
    
    Slides --> SlidesTool[Google Slides API]
    Slides --> LayoutTool[Layout Engine]
    Slides --> ThemeTool[Theme Presets]
    Slides --> ImageTool[Image Placement]
```

### Agent Execution Pipeline

```mermaid
flowchart TB
    Start([User Request]) --> Validate{Valid Request?}
    Validate -->|No| Error[Return Error]
    Validate -->|Yes| Queue[Queue Celery Task]
    
    Queue --> Worker[Celery Worker Picks Up]
    Worker --> Init[Initialize Agent]
    Init --> LoadMem[Load Conversation Memory]
    LoadMem --> LoadTools[Load Agent Tools]
    LoadTools --> Trace[Start LangFuse Trace]
    
    Trace --> Execute[Execute Agent Chain]
    Execute --> LLM{LLM Decision}
    
    LLM -->|Use Tool| Tool[Execute Tool]
    Tool --> GWS{Google API Call?}
    GWS -->|Yes| Auth[Check OAuth Token]
    Auth --> Refresh{Token Valid?}
    Refresh -->|No| RotateToken[Rotate Token]
    Refresh -->|Yes| CallAPI[Call Google API]
    RotateToken --> CallAPI
    CallAPI --> Result[Tool Result]
    GWS -->|No| Result
    
    Result --> Log[Log to LangFuse]
    Log --> LLM
    
    LLM -->|Final Answer| Complete[Complete Task]
    Complete --> SaveMem[Save Memory]
    SaveMem --> Budget[Update Budget]
    Budget --> Notify[Notify User]
    Notify --> End([Task Complete])
    
    Error --> End
```

---

## Data Flow

### Request/Response Flow

```mermaid
sequenceDiagram
    participant Client
    participant Nginx as Nginx/Load Balancer
    participant FastAPI
    participant Redis
    participant Celery
    participant Postgres
    participant Agent
    participant Google

    Client->>Nginx: HTTPS Request
    Nginx->>FastAPI: Forward Request
    
    FastAPI->>Redis: Check Cache
    alt Cache Hit
        Redis-->>FastAPI: Cached Response
        FastAPI-->>Client: 200 OK (Cached)
    else Cache Miss
        FastAPI->>Postgres: Query Data
        Postgres-->>FastAPI: Data
        
        alt Async Task Required
            FastAPI->>Redis: Enqueue Task
            Redis->>Celery: Task Notification
            FastAPI-->>Client: 202 Accepted
            
            Celery->>Agent: Execute Agent
            Agent->>Google: API Calls
            Google-->>Agent: Results
            Agent->>Postgres: Save Results
            Agent->>Redis: Cache Results
            Celery-->>Client: WebSocket Update
        else Sync Response
            FastAPI->>Redis: Cache Response
            FastAPI-->>Client: 200 OK
        end
    end
```

### Memory Management Flow

```mermaid
graph TB
    subgraph "Memory System"
        Input[User Message] --> MemMgr[MemoryManager]
        
        MemMgr --> ConvMem[ConversationMemory<br/>Short-term]
        MemMgr --> VecMem[VectorMemory<br/>Long-term]
        
        ConvMem --> Buffer[Conversation Buffer<br/>Recent Messages]
        Buffer --> DB[(PostgreSQL<br/>conversations table)]
        
        VecMem --> Embed[Embedding Generator<br/>text-embedding-3-small]
        Embed --> Vector[(PGVector<br/>vector_memory table)]
        
        Vector --> Search[Semantic Search<br/>Cosine Similarity]
        Search --> Retrieve[Context Retrieval]
        
        Retrieve --> Agent[Agent Context]
        Agent --> LLM[LLM with Context]
    end
```

### Budget Tracking Flow

```mermaid
sequenceDiagram
    participant Agent
    participant LangFuse
    participant BudgetSvc as BudgetService
    participant DB as PostgreSQL
    participant Beat as Celery Beat
    participant Email as Email Service

    Agent->>LangFuse: Log LLM Call
    LangFuse->>BudgetSvc: Receive Callback
    BudgetSvc->>BudgetSvc: Calculate Cost
    Note over BudgetSvc: input_tokens * $0.01/1K<br/>output_tokens * $0.03/1K
    BudgetSvc->>DB: Save Usage Record
    
    loop Every Hour
        Beat->>BudgetSvc: Check Budgets
        BudgetSvc->>DB: Query Total Usage
        BudgetSvc->>BudgetSvc: Compare vs. Limit
        
        alt Exceeded 80%
            BudgetSvc->>Email: Send Warning
        end
        
        alt Exceeded 100%
            BudgetSvc->>Email: Send Alert
            BudgetSvc->>DB: Disable User/Agent
        end
    end
```

---

## Authentication Flow

### OAuth 2.0 Flow (Google)

```mermaid
sequenceDiagram
    participant User
    participant Client as Client App
    participant Backend as FastAPI
    participant Google as Google OAuth
    participant DB as PostgreSQL

    User->>Client: Click "Sign in with Google"
    Client->>Backend: GET /api/v1/oauth/authorize
    Backend->>Backend: Generate state + PKCE
    Backend->>DB: Save state
    Backend-->>Client: Redirect URL
    
    Client->>Google: Redirect to Google
    User->>Google: Authorize App
    Google-->>Client: Redirect with code
    
    Client->>Backend: POST /api/v1/oauth/callback
    Backend->>DB: Verify state
    Backend->>Google: Exchange code for tokens
    Google-->>Backend: access_token + refresh_token
    
    Backend->>Backend: Encrypt tokens
    Backend->>DB: Save encrypted tokens
    Backend->>Backend: Generate JWT
    Backend-->>Client: JWT token
    
    Client->>Client: Store JWT
    Client->>Backend: API calls with JWT
```

### Token Rotation Flow (Enhanced OAuth)

```mermaid
flowchart TB
    Start([API Request]) --> Auth{JWT Valid?}
    Auth -->|No| Reject[401 Unauthorized]
    Auth -->|Yes| CheckScope[Check OAuth Scopes]
    
    CheckScope --> GetToken[Get Access Token]
    GetToken --> ValidToken{Token Valid?}
    
    ValidToken -->|Yes| UseToken[Use Token]
    ValidToken -->|No| HasRefresh{Has Refresh Token?}
    
    HasRefresh -->|No| ReAuth[Require Re-authentication]
    HasRefresh -->|Yes| Rotate[Rotate Tokens]
    
    Rotate --> Request[Request New Tokens]
    Request --> Encrypt[Encrypt New Tokens]
    Encrypt --> Save[Save to DB]
    Save --> Detect{Reuse Detected?}
    
    Detect -->|Yes| Revoke[Revoke All Tokens]
    Detect -->|No| UseToken
    
    UseToken --> API[Call Google API]
    API --> Success([Success])
    
    Reject --> End([End])
    ReAuth --> End
    Revoke --> End
```

### Multi-Provider OAuth

```mermaid
graph TB
    User[User Request] --> Provider{OAuth Provider}
    
    Provider -->|Google| GoogleFlow[Google OAuth Flow]
    Provider -->|GitHub| GitHubFlow[GitHub OAuth Flow]
    Provider -->|Microsoft| MSFlow[Microsoft OAuth Flow]
    
    GoogleFlow --> Scopes1[Workspace Scopes]
    GitHubFlow --> Scopes2[Repo Scopes]
    MSFlow --> Scopes3[Office 365 Scopes]
    
    Scopes1 --> Store[TokenStore]
    Scopes2 --> Store
    Scopes3 --> Store
    
    Store --> Encrypt[AES-256 Encryption]
    Encrypt --> DB[(PostgreSQL<br/>oauth_tokens)]
    
    DB --> Celery[Celery Task:<br/>Auto Rotation]
    Celery --> Monitor[Token Monitor]
    Monitor --> Cleanup{Expired?}
    Cleanup -->|Yes| Delete[Delete Token]
    Cleanup -->|No| Keep[Keep Token]
```

---

## Mobile Architecture

### Flutter App Architecture (MVVM Pattern)

```mermaid
graph TB
    subgraph "Presentation Layer"
        UI[Screens/Widgets]
        VM[ViewModels<br/>Provider/Riverpod]
    end
    
    subgraph "Domain Layer"
        UC[Use Cases]
        Repo[Repository Interface]
    end
    
    subgraph "Data Layer"
        RepoImpl[Repository Implementation]
        API[API Client]
        Local[Local Storage<br/>SQLite]
        Sync[SyncQueueService]
    end
    
    subgraph "External"
        Backend[FastAPI Backend]
        GoogleAuth[Google OAuth]
    end
    
    UI --> VM
    VM --> UC
    UC --> Repo
    Repo --> RepoImpl
    RepoImpl --> API
    RepoImpl --> Local
    RepoImpl --> Sync
    API --> Backend
    API --> GoogleAuth
    Sync --> Backend
```

### Offline Sync Architecture

```mermaid
sequenceDiagram
    participant User
    participant UI
    participant ViewModel
    participant Repo as Repository
    participant SyncQueue as SyncQueueService
    participant Local as SQLite
    participant API as Backend API

    User->>UI: Create Conversation
    UI->>ViewModel: createConversation()
    ViewModel->>Repo: createConversation()
    
    alt Online Mode
        Repo->>API: POST /conversations
        API-->>Repo: Response (ID: 123)
        Repo->>Local: Save with ID 123
        Repo-->>ViewModel: Success
    else Offline Mode
        Repo->>Local: Save with temp ID (temp_xyz)
        Repo->>SyncQueue: Queue create operation
        SyncQueue->>Local: Save to sync_queue
        Repo-->>ViewModel: Success (optimistic)
    end
    
    ViewModel-->>UI: Update UI
    
    Note over SyncQueue: Device goes online
    
    SyncQueue->>API: POST /conversations
    API-->>SyncQueue: Response (ID: 123)
    SyncQueue->>Local: Replace temp_xyz with 123
    SyncQueue->>Local: Mark synced
    SyncQueue-->>UI: Notify sync complete
```

### Mobile Data Flow

```mermaid
flowchart TB
    Start([User Action]) --> Network{Network Available?}
    
    Network -->|Yes| Online[Online Mode]
    Network -->|No| Offline[Offline Mode]
    
    Online --> API[Call Backend API]
    API --> Cache[Update Local Cache]
    Cache --> UI[Update UI]
    
    Offline --> TempID[Generate Temp ID]
    TempID --> LocalSave[Save to SQLite]
    LocalSave --> Queue[Add to Sync Queue]
    Queue --> UIOptimistic[Update UI<br/>Optimistic]
    
    UIOptimistic --> Monitor[Monitor Network]
    Monitor --> Reconnect{Network Restored?}
    
    Reconnect -->|Yes| ProcessQueue[Process Sync Queue]
    ProcessQueue --> BatchSync[Batch Sync Operations]
    BatchSync --> Retry{Success?}
    
    Retry -->|Yes| UpdateLocal[Update Local IDs]
    Retry -->|No| RetryCount{Retry < 3?}
    
    RetryCount -->|Yes| Wait[Wait & Retry]
    RetryCount -->|No| Failed[Mark Failed]
    
    Wait --> ProcessQueue
    UpdateLocal --> Done([Complete])
    Failed --> Done
    UI --> Done
    
    Reconnect -->|No| Monitor
```

---

## Database Schema

### Core Tables

```mermaid
erDiagram
    users ||--o{ conversations : has
    users ||--o{ agents : owns
    users ||--o{ oauth_tokens : has
    users ||--o{ budget_limits : has
    users ||--o{ llm_usage : tracks
    
    conversations ||--o{ messages : contains
    conversations ||--o{ tasks : creates
    
    agents ||--o{ tasks : executes
    
    tasks ||--o{ llm_usage : generates
    
    users {
        uuid id PK
        string email UK
        string name
        string password_hash
        boolean is_active
        timestamp created_at
        timestamp last_login
    }
    
    conversations {
        uuid id PK
        uuid user_id FK
        string title
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    messages {
        uuid id PK
        uuid conversation_id FK
        string role
        text content
        jsonb metadata
        timestamp created_at
    }
    
    agents {
        uuid id PK
        uuid user_id FK
        string name
        string type
        jsonb config
        boolean is_active
        timestamp created_at
    }
    
    tasks {
        uuid id PK
        uuid conversation_id FK
        uuid agent_id FK
        string status
        text input
        text output
        jsonb metadata
        timestamp created_at
        timestamp completed_at
    }
    
    oauth_tokens {
        uuid id PK
        uuid user_id FK
        string provider
        text access_token_encrypted
        text refresh_token_encrypted
        jsonb scopes
        timestamp expires_at
        timestamp created_at
    }
    
    budget_limits {
        uuid id PK
        uuid user_id FK
        decimal daily_limit
        decimal monthly_limit
        boolean enabled
    }
    
    llm_usage {
        uuid id PK
        uuid user_id FK
        uuid task_id FK
        string model
        int input_tokens
        int output_tokens
        decimal cost
        timestamp created_at
    }
```

### Vector Memory Schema

```mermaid
erDiagram
    vector_memory {
        uuid id PK
        uuid user_id FK
        uuid conversation_id FK
        text content
        vector embedding
        jsonb metadata
        timestamp created_at
    }
    
    citations {
        uuid id PK
        uuid task_id FK
        string source_url
        string source_title
        text excerpt
        string citation_style
        int order_index
        timestamp created_at
    }
```

---

## Technology Stack

### Backend Stack

```mermaid
graph TB
    subgraph "Web Framework"
        FastAPI[FastAPI 0.104+]
        Pydantic[Pydantic 2.0+]
        Uvicorn[Uvicorn ASGI Server]
    end
    
    subgraph "Agent Framework"
        LangChain[LangChain 0.1+]
        LangFuse[LangFuse 2.6+]
    end
    
    subgraph "Task Queue"
        Celery[Celery 5.3+]
        Beat[Celery Beat]
    end
    
    subgraph "Database"
        Postgres[PostgreSQL 15+]
        PGVector[PGVector Extension]
        SQLAlchemy[SQLAlchemy 2.0+]
    end
    
    subgraph "Cache & Queue"
        Redis[Redis 7+]
    end
    
    subgraph "LLM Providers"
        OpenAI[OpenAI API]
        Claude[Anthropic Claude]
    end
    
    subgraph "External APIs"
        Google[Google Workspace APIs]
        Weather[OpenWeatherMap]
    end
```

### Frontend Stack

```mermaid
graph TB
    subgraph "Web"
        React[React 18+]
        Next[Next.js 14+]
        TailwindCSS
    end
    
    subgraph "Desktop"
        Tauri[Tauri 1.5+]
        Rust[Rust Backend]
        WebView2
    end
    
    subgraph "Mobile"
        Flutter[Flutter 3.16+]
        Dart[Dart 3.0+]
        Provider[Provider/Riverpod]
    end
    
    subgraph "State Management"
        Zustand[Zustand - Web]
        TauriState[Tauri State - Desktop]
        FlutterProvider[Provider - Mobile]
    end
```

### Deployment Stack

```mermaid
graph TB
    subgraph "Infrastructure"
        Docker[Docker Containers]
        Compose[Docker Compose]
        Nginx[Nginx Reverse Proxy]
    end
    
    subgraph "Services"
        BackendService[FastAPI Service]
        CeleryService[Celery Workers]
        BeatService[Celery Beat]
        PostgresService[PostgreSQL]
        RedisService[Redis]
    end
    
    subgraph "Monitoring"
        LangFuse[LangFuse Dashboard]
        Prometheus[Prometheus Metrics]
        Grafana[Grafana Dashboards]
    end
    
    subgraph "CI/CD"
        GitHub[GitHub Actions]
        Tests[Pytest Tests]
        Deploy[Auto Deploy]
    end
```

---

## Performance Considerations

### Caching Strategy

```mermaid
flowchart LR
    Request[API Request] --> CheckCache{Cache Hit?}
    
    CheckCache -->|Yes| Redis[(Redis Cache)]
    CheckCache -->|No| DB[(PostgreSQL)]
    
    Redis --> Return[Return Cached]
    DB --> Process[Process Query]
    Process --> Store[Store in Cache]
    Store --> Return
    
    Return --> Response[API Response]
```

**Cache TTL Policy:**
- User sessions: 24 hours
- Conversation history: 1 hour
- Agent configs: 6 hours
- OAuth tokens: Until expiry
- Search results: 30 minutes

### Scaling Strategy

```mermaid
graph TB
    subgraph "Horizontal Scaling"
        LB[Load Balancer]
        API1[FastAPI Instance 1]
        API2[FastAPI Instance 2]
        API3[FastAPI Instance N]
        
        LB --> API1
        LB --> API2
        LB --> API3
    end
    
    subgraph "Worker Scaling"
        Queue[(Redis Queue)]
        W1[Celery Worker 1]
        W2[Celery Worker 2]
        W3[Celery Worker N]
        
        Queue --> W1
        Queue --> W2
        Queue --> W3
    end
    
    subgraph "Data Layer"
        Master[(PostgreSQL Master)]
        Replica1[(Read Replica 1)]
        Replica2[(Read Replica 2)]
        
        Master --> Replica1
        Master --> Replica2
    end
    
    API1 --> Queue
    API2 --> Queue
    API3 --> Queue
    
    API1 --> Master
    API1 --> Replica1
    API2 --> Replica2
```

---

## Security Architecture

### Security Layers

```mermaid
graph TB
    subgraph "Network Layer"
        HTTPS[HTTPS/TLS 1.3]
        CORS[CORS Policy]
        RateLimit[Rate Limiting]
    end
    
    subgraph "Authentication"
        JWT[JWT Tokens]
        OAuth[OAuth 2.0 + PKCE]
        MFA[MFA Support]
    end
    
    subgraph "Authorization"
        RBAC[Role-Based Access Control]
        Scopes[OAuth Scopes]
        Policies[Resource Policies]
    end
    
    subgraph "Data Security"
        Encryption[AES-256 Encryption]
        Hashing[Argon2 Hashing]
        Tokenization[Token Encryption]
    end
    
    subgraph "API Security"
        Validation[Input Validation]
        Sanitization[SQL Injection Prevention]
        CSRF[CSRF Protection]
    end
    
    HTTPS --> JWT
    JWT --> RBAC
    RBAC --> Validation
    OAuth --> Encryption
    Encryption --> Tokenization
```

---

## Deployment Architecture

### Production Environment

```mermaid
graph TB
    subgraph "Edge"
        CDN[Cloudflare CDN]
        WAF[Web Application Firewall]
    end
    
    subgraph "Application Layer"
        Nginx[Nginx Load Balancer]
        API1[FastAPI Container 1]
        API2[FastAPI Container 2]
        Worker1[Celery Worker 1]
        Worker2[Celery Worker 2]
    end
    
    subgraph "Data Layer"
        PostgresPrimary[(PostgreSQL Primary)]
        PostgresReplica[(PostgreSQL Replica)]
        RedisCluster[(Redis Cluster)]
    end
    
    subgraph "External"
        S3[S3 Storage]
        CloudWatch[CloudWatch Logs]
        LangFuse[LangFuse SaaS]
    end
    
    CDN --> WAF
    WAF --> Nginx
    Nginx --> API1
    Nginx --> API2
    API1 --> Worker1
    API2 --> Worker2
    API1 --> PostgresPrimary
    API2 --> PostgresReplica
    Worker1 --> RedisCluster
    Worker2 --> RedisCluster
    API1 --> S3
    Worker1 --> CloudWatch
    Worker1 --> LangFuse
```

---

## Monitoring & Observability

### Observability Stack

```mermaid
graph LR
    subgraph "Application"
        FastAPI[FastAPI]
        Celery[Celery Workers]
        Agents[LangChain Agents]
    end
    
    subgraph "Metrics"
        Prometheus[Prometheus]
        Grafana[Grafana]
    end
    
    subgraph "Logging"
        Logs[Application Logs]
        CloudWatch[CloudWatch/ELK]
    end
    
    subgraph "Tracing"
        LangFuse[LangFuse]
        OpenTelemetry[OpenTelemetry]
    end
    
    FastAPI --> Prometheus
    Celery --> Prometheus
    Prometheus --> Grafana
    
    FastAPI --> Logs
    Celery --> Logs
    Logs --> CloudWatch
    
    Agents --> LangFuse
    FastAPI --> OpenTelemetry
```

**Key Metrics Tracked:**
- Request latency (p50, p95, p99)
- Error rates (4xx, 5xx)
- Agent execution time
- LLM token usage & cost
- Task queue depth
- Database query performance
- Cache hit ratio

---

## Future Architecture Enhancements

### Planned Improvements

1. **GraphQL API Layer** - More flexible queries for complex clients
2. **Event-Driven Architecture** - Kafka/RabbitMQ for event streaming
3. **Service Mesh** - Istio for microservices communication
4. **Multi-Region Deployment** - Global CDN + database replication
5. **ML Model Serving** - Custom fine-tuned models via TensorFlow Serving
6. **Real-time Collaboration** - Operational Transform for multi-user editing
7. **Vector Database Migration** - Pinecone/Weaviate for advanced semantic search

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangChain Documentation](https://python.langchain.com/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Google Workspace APIs](https://developers.google.com/workspace)
- [LangFuse Documentation](https://langfuse.com/docs)

---

**Document Version**: 1.0  
**Last Review**: 2026-03-01  
**Next Review**: 2026-04-01
