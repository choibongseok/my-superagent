# 🚀 AgentHQ - Multi-Client AI Automation Platform

> Google Workspace 기반의 멀티 에이전트 자동화 시스템

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.1+-purple.svg)](https://python.langchain.com/)
[![LangFuse](https://img.shields.io/badge/LangFuse-2.6+-teal.svg)](https://langfuse.com/)
[![Tauri](https://img.shields.io/badge/Tauri-1.5+-orange.svg)](https://tauri.app/)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-blue.svg)](https://flutter.dev/)
[![Test Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)](https://github.com/choibongseok/my-superagent)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/choibongseok/my-superagent/pulls)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Desktop Setup](#desktop-setup)
  - [Mobile Setup](#mobile-setup)
- [Configuration](#-configuration)
  - [Google OAuth](#google-oauth-setup)
  - [Environment Variables](#environment-variables)
- [API Documentation](#-api-documentation)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Development Status](#-development-status)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)

---

## 🌟 Overview

**AgentHQ**는 Google Workspace 작업을 자동화하는 멀티 에이전트 시스템입니다.
자연어 명령만으로 문서 작성, 데이터 분석, 프레젠테이션 제작 등을 처리합니다.

**주요 특징**:
- 📊 자연어 → Google Sheets 자동 생성
- 📝 인용 출처 포함한 Docs 리포트 작성
- 🎨 Slides 프레젠테이션 자동 디자인
- 🔍 웹 검색 기반 리서치 및 분석
- 🧠 대화 컨텍스트 유지 (Multi-turn Conversations)
- 🤝 Google Workspace 전체 통합

**기술 하이라이트**:
- LangChain 기반 Agent 아키텍처
- LangFuse를 통한 LLM 모니터링
- Desktop / Mobile / Web 멀티플랫폼 지원
- Enterprise-Grade 설계 (보안, 확장성, 안정성)

---

## ✨ Features

### Core Capabilities

#### 1. Intelligent Document Generation
- **Google Docs**: 구조화된 리포트 자동 생성, 인용 관리
- **Google Sheets** (520+ 라인 고급 기능): 
  - 데이터 입력 및 자동 분석
  - 셀 서식 지정 (bold, italic, currency, percent, background colors)
  - 차트 자동 생성 (LINE, BAR, COLUMN, PIE, AREA, SCATTER)
  - 자동 서식 지능형 적용
- **Google Slides** (312 라인 고급 기능): 
  - 프레젠테이션 자동 구성
  - 텍스트/이미지 삽입 (위치 커스터마이징)
  - 발표자 노트 추가
  - 색상 테마 적용 (6가지 프리셋: Modern, Ocean, Sunset, Forest, Coral, Monochrome)

#### 2. Research & Analysis
- 웹 검색 및 정보 수집 (OpenWeatherMap 통합)
- 다중 소스 교차 검증
- 자동 인용 및 참고 문헌 생성 (APA, MLA, Chicago 스타일)
- Citation 통계 및 Source 관리

#### 3. Memory & Context
- **MemoryManager**: ConversationMemory + VectorMemory 통합
- 시맨틱 검색 기반 장기 메모리 (PGVector)
- 컨텍스트 기반 Follow-up 지원
- Multi-turn conversation 히스토리 관리

#### 4. Multi-Platform Access
- **Desktop**: Tauri 네이티브 앱 (Windows, macOS, Linux)
- **Mobile**: Flutter 앱 (iOS, Android) - **완전히 구현됨** ✅
  - Google OAuth 인증 (ID token 검증)
  - **완전한 오프라인 모드** (533 라인 구현)
    - SyncQueueService: 오프라인 작업 큐잉
    - Auto-sync: 온라인 복귀 시 자동 동기화
    - Optimistic updates: Temporary ID로 즉시 UI 업데이트
    - Retry logic: 최대 3회 재시도
    - Sync 상태 스트림 (실시간 UI 업데이트)
  - LocalCache 서비스 (오프라인 fallback)
- **Web**: (Planned) 브라우저 지원

#### 5. Template System
- Task 템플릿 기반 빠른 작업 생성
- Category → Task Type 자동 매핑
- **Template-Task 통합** (Phase 1 완료):
  - Template 사용 시 실제 Task 자동 생성
  - Celery worker 자동 배정
  - 8개 통합 테스트 시나리오
- Metadata 및 inputs 저장

#### 6. Advanced LLM Integration (Sprint 6 ✅)
- **Multi-Model Support**:
  - OpenAI GPT-4 / GPT-4o
  - **Anthropic Claude** (Opus, Sonnet 4.5, Haiku) - 완전 지원
  - Per-agent model selection
  - Automatic fallback handling
- **Budget Tracking & Alerts** (Sprint 5 ✅):
  - Real-time LLM cost monitoring (OpenAI + Claude)
  - User/Project budget limits with alerts
  - Celery task for daily budget monitoring
  - Cost projection & usage analytics
- **Fact Checking Service** (375 라인):
  - Multi-source verification
  - Wikipedia + Britannica integration
  - Confidence scoring (0-100)
  - Verification metadata tracking

#### 7. Enhanced Security & OAuth (Sprint 7 ✅)
- **OAuth Token Management**:
  - Automatic refresh token rotation
  - Multi-provider support (Google, GitHub, Microsoft)
  - Token encryption at rest (Fernet)
  - Reuse detection for security
  - Celery task for token cleanup (90-day expiry)
- **보안 강화**: 
  - 9개 메서드에서 `eval()` 제거 (코드 인젝션 방지)
  - JWT 기반 인증 (access + refresh tokens)
  - Google ID token 검증

#### 8. Enterprise Automation
- **Multi-agent orchestration**: 복잡한 작업 자동 분배 및 조율
- **Celery 비동기 Task Queue**: 자동 큐잉 + 실시간 상태 동기화
- **Celery Beat Scheduling** (Sprint 4 ✅):
  - Periodic task scheduling (daily/weekly/custom)
  - Usage nudge emails (weekly inactive users)
  - Budget monitoring automation
  - Token cleanup automation
- **LocalCache 서비스**: 성능 최적화 + 오프라인 지원
- **Email Service** (389 라인 구현):
  - SMTP 기반 workspace invitation
  - 프로페셔널한 HTML 템플릿 (반응형 디자인)
  - Plain text fallback
  - 8개 테스트 시나리오
- **WebSocket 재연결 로직**: 네트워크 단절 후 자동 복구
- **25+ E2E 통합 테스트**: full workflow + multi-agent orchestration

---

## 🧱 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentHQ Architecture                      │
├─────────────────┬───────────────┬───────────────┬───────────┤
│   Desktop       │   Mobile      │   Backend     │  Storage  │
│   (Tauri)       │   (Flutter)   │   (FastAPI)   │  (Google) │
├─────────────────┼───────────────┼───────────────┼───────────┤
│ React 기반 UI   │ iOS / Android │ Auth           │ Docs      │
│ OAuth           │ OAuth         │ Agents         │ Sheets    │
│ Native 배포     │               │ Task Queue     │ Slides    │
│                 │               │ Memory         │ Drive     │
└─────────────────┴───────────────┴───────────────┴───────────┘
```

### Component Overview

**Frontend Clients**:
- Desktop app (Tauri + React)
- Mobile app (Flutter)
- Unified API communication

**Backend Services**:
- FastAPI REST API
- Celery task queue
- LangChain agent orchestration
- Memory management (Conversation + Vector)

**External Integrations**:
- Google Workspace APIs
- OpenAI / Anthropic LLMs
- LangFuse observability

---

## 🛠 Tech Stack

| Category          | Technologies                                           |
| ----------------- | ------------------------------------------------------ |
| **Backend**       | FastAPI, Celery, Celery Beat, PostgreSQL (+PGVector), Redis |
| **Agent System**  | LangChain, OpenAI GPT-4/GPT-4o, Anthropic Claude (Opus/Sonnet/Haiku) |
| **Memory**        | ConversationMemory, VectorStoreMemory (PGVector)       |
| **Observability** | LangFuse (LLM tracing, cost tracking, budget alerts)   |
| **Security**      | JWT auth, OAuth token encryption (Fernet), Google ID validation |
| **Desktop**       | Tauri 1.5+, React 18, TypeScript, Tailwind CSS         |
| **Mobile**        | Flutter 3.16+, Dart                                    |
| **Infrastructure**| Docker, Cloud Run, GCS, Terraform                      |
| **Testing**       | pytest, pytest-asyncio, Flutter test, E2E test suite (25+ scenarios) |

---

## ⚡ Quick Start (원클릭 실행)

### 1. Docker Desktop 설치
- Mac/Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### 2. 실행
```bash
# 저장소 클론
git clone https://github.com/choibongseok/my-superagent.git
cd my-superagent

# 개발 환경 시작 (원클릭)
./scripts/dev.sh

# 접속
# Backend API: http://localhost:8000
# API Docs:    http://localhost:8000/docs
# Celery Monitor: http://localhost:5555
```

### 3. 종료
```bash
./scripts/stop.sh
```

**포함된 서비스**:
- ✅ Backend API (FastAPI) with hot reload
- ✅ PostgreSQL + pgvector
- ✅ Redis (cache & message broker)
- ✅ Celery Worker (agent tasks)
- ✅ Celery Flower (monitoring)

> 📚 상세 가이드: [DEV_GUIDE.md](docs/DEV_GUIDE.md)

---

## 🚀 Getting Started

### Prerequisites

```bash
# Required
- Python 3.11+
- Node.js 18+
- Rust 1.70+ (for Tauri)
- Flutter 3.16+ (for mobile)
- Docker & Docker Compose
- Google Cloud CLI

# Optional
- PostgreSQL 15+
- Redis 7+
```

---

### Backend Setup

```bash
# 1. Clone repository
git clone https://github.com/choibongseok/my-superagent.git
cd my-superagent/backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your credentials (see Configuration section)

# 5. Run database migrations
alembic upgrade head

# 6. Start development server
uvicorn app.main:app --reload --port 8000
```

**Verify**: http://localhost:8000/docs (Swagger UI)

---

### Desktop Setup

```bash
cd desktop

# Install dependencies
npm install

# Run development mode
npm run tauri dev

# Build for production
npm run tauri build
```

**Output**: Binaries in `src-tauri/target/release/bundle/`

---

### Mobile Setup

```bash
cd mobile

# Get dependencies
flutter pub get

# Run on device/emulator
flutter run

# Build release
flutter build apk --release  # Android
flutter build ios --release  # iOS (requires macOS + Xcode)
```

---

## ⚙️ Configuration

### Google OAuth Setup

#### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project: **AgentHQ**
3. Enable APIs:
   - Google Docs API
   - Google Sheets API
   - Google Slides API
   - Google Drive API

#### 2. Configure OAuth Consent Screen
```
Application name: AgentHQ
User support email: your-email@example.com
Scopes:
  - .../auth/documents
  - .../auth/spreadsheets
  - .../auth/presentations
  - .../auth/drive.file
```

#### 3. Create OAuth 2.0 Credentials
- **Desktop**: Application type → Desktop app
- Download JSON → Save as `backend/credentials.json`

📖 **Detailed guide**: [docs/OAUTH_SETUP.md](docs/OAUTH_SETUP.md)

---

### Environment Variables

```bash
# backend/.env

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# LangChain
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=agenthq

# LangFuse (LLM Observability & Budget Tracking)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# OAuth Token Encryption (Fernet)
OAUTH_ENCRYPTION_KEY=your-fernet-key-here  # Generate with cryptography.fernet.Fernet.generate_key()

# Budget Alerts (Sprint 5)
BUDGET_ALERT_THRESHOLD=0.8  # Alert at 80% of budget
BUDGET_CHECK_INTERVAL=86400  # Daily (seconds)

# Database & Cache
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/agenthq
REDIS_URL=redis://localhost:6379/0

# SMTP Email (for alerts & invitations)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# App Settings
DEBUG=true
LOG_LEVEL=INFO
```

🔧 **Full reference**: [backend/.env.example](backend/.env.example)

---

## 📡 API Documentation

### Core Endpoints

```http
# Task Management
POST   /api/v1/tasks              # Create new task
GET    /api/v1/tasks/{id}         # Get task status
GET    /api/v1/tasks/{id}/result  # Get task result
DELETE /api/v1/tasks/{id}         # Cancel task

# Authentication
GET    /api/v1/auth/google        # Initiate OAuth flow
GET    /api/v1/auth/callback      # OAuth callback
POST   /api/v1/auth/refresh       # Refresh access token

# Memory
GET    /api/v1/memory             # Get conversation history
POST   /api/v1/memory             # Save memory
DELETE /api/v1/memory/{id}        # Clear memory

# Health
GET    /api/v1/ping               # Health check
GET    /api/v1/status             # Service status
```

### Example: Create Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a quarterly sales report for Q4 2024",
    "output_type": "docs"
  }'
```

**Response**:
```json
{
  "task_id": "uuid-here",
  "status": "pending",
  "created_at": "2024-10-29T00:00:00Z"
}
```

📚 **Interactive API Docs**: http://localhost:8000/docs

---

## 🧪 Testing

### Run Tests

```bash
# Backend
cd backend
pytest tests/ -v --cov=app --cov-report=html

# Desktop
cd desktop
npm test

# Mobile
cd mobile
flutter test
```

### Test Coverage

Current coverage: **85%+**

- Memory System: 95%
- Citation System: 90%
- Core APIs: 80%
- **E2E Integration Tests**: 25+ scenarios (870 lines)
  - Agent full workflows (Research, Docs, Sheets, Slides)
  - Multi-agent orchestration
  - Task lifecycle testing
  - Error handling & recovery
  - Template execution
  - Cache integration
  - Concurrent execution

📊 **Coverage Report**: `backend/htmlcov/index.html`

---

## 🚢 Deployment

### Backend (Cloud Run)

```bash
cd backend

# Build container
docker build -t gcr.io/your-project/agenthq-backend:latest .

# Push to registry
docker push gcr.io/your-project/agenthq-backend:latest

# Deploy
gcloud run deploy agenthq-backend \
  --image gcr.io/your-project/agenthq-backend:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Desktop (Tauri)

```bash
cd desktop
npm run tauri build

# Binaries:
# - macOS: src-tauri/target/release/bundle/dmg/
# - Windows: src-tauri/target/release/bundle/msi/
# - Linux: src-tauri/target/release/bundle/appimage/
```

### Mobile (Flutter)

```bash
cd mobile

# Android
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk

# iOS (requires macOS + Xcode)
flutter build ipa --release
# Output: build/ios/archive/Runner.xcarchive
```

---

## 🚧 Development Status

**Current Sprint**: Sprint 8 Complete ✅ | **Status**: Production Ready

**Completed**:
- ✅ **Phase 1**: Core API, OAuth, Database, Task Queue
- ✅ **Phase 2**: LangChain integration, Memory system, Citation tracking
- ✅ **Phase 3**: Modern Chat UI (4-column layout, Dark mode, Guest mode)
- ✅ **Phase 3-1**: Mobile Client (Flutter) - iOS/Android apps with OAuth + Offline Mode
- ✅ **Sprint 2**: Usage Nudge Emails (2026-02-26)
- ✅ **Sprint 3**: Enhanced Docs Agent
- ✅ **Sprint 4**: Smart Scheduling with Celery Beat
- ✅ **Sprint 5**: LLM Cost Tracking & Budget Alerts (2026-03-01)
- ✅ **Sprint 6**: Claude/Anthropic Integration (2026-03-01)
- ✅ **Sprint 7**: Enhanced OAuth with Token Rotation & Encryption (2026-03-01)
- ✅ **Sprint 8**: Sheets Advanced Features - Formulas, Pivot Tables, Conditional Formatting (2026-03-01)

**Sprint 5-8 주요 성과** (2026-03-01):
- ✅ **Multi-Model LLM Support**
  - Anthropic Claude (Opus, Sonnet 4.5, Haiku) 완전 통합
  - Per-agent model selection
  - Budget tracking for all models (OpenAI + Claude)
- ✅ **Budget Management System**
  - Real-time cost monitoring
  - User/Project budget limits & alerts
  - Daily monitoring via Celery Beat
  - Cost projection & analytics
- ✅ **Enhanced OAuth Security**
  - Automatic refresh token rotation
  - Multi-provider support (Google, GitHub, Microsoft)
  - Token encryption at rest (Fernet)
  - Reuse detection & automatic cleanup
- ✅ **Sheets Agent Advanced Features** (520+ lines)
  - Formulas: SUM, AVERAGE, VLOOKUP, etc.
  - Pivot tables & data analysis
  - Conditional formatting
  - Data validation & named ranges
- ✅ **Fact Checking Service** (375 lines)
  - Multi-source verification
  - Confidence scoring
  - Wikipedia + Britannica integration
- ✅ **Celery Beat Automation**
  - Usage nudge emails (weekly)
  - Budget monitoring (daily)
  - Token cleanup (daily)

**Remaining Documentation Tasks**:
- 📍 API documentation for new endpoints (Sprint 6-8)
- 📍 Developer onboarding guide
- 📍 Architecture diagrams update

📋 **Sprint Reports**: 
- [Sprint 8 Completion](docs/SPRINT_8_COMPLETION.md)
- [Sprint 7 Completion](docs/SPRINT_7_COMPLETION.md)
- [Sprint 6 Completion](docs/SPRINT_6_COMPLETION.md)

---

## 📖 Documentation

### Architecture & Planning
- **[🏗️ ARCHITECTURE.md](docs/ARCHITECTURE.md)** - 시스템 아키텍처 상세 설계
- **[📊 PHASE_PLAN.md](docs/PHASE_PLAN.md)** - 전체 개발 로드맵 (Phase 0-6)
- **[📝 OAUTH_SETUP.md](docs/OAUTH_SETUP.md)** - Google OAuth 설정 가이드

### Implementation Guides
- **[🔧 PHASE_0_IMPLEMENTATION.md](docs/PHASE_0_IMPLEMENTATION.md)** - LangChain/LangFuse 통합
- **[🧠 PHASE_2_IMPLEMENTATION.md](docs/PHASE_2_IMPLEMENTATION.md)** - Memory & Citation 시스템
- **[🔗 LANGCHAIN_GUIDE.md](docs/LANGCHAIN_GUIDE.md)** - LangChain 개념 및 구현 패턴
- **[📊 LANGFUSE_SETUP.md](docs/LANGFUSE_SETUP.md)** - LangFuse 모니터링 시스템

### Feature Documentation (Sprint 5-8)
- **[🤖 CLAUDE_INTEGRATION.md](docs/CLAUDE_INTEGRATION.md)** - Anthropic Claude 통합 (Sprint 6)
- **[🔐 ENHANCED_OAUTH.md](docs/ENHANCED_OAUTH.md)** - OAuth Token Rotation & Encryption (Sprint 7)
- **[📊 SHEETS_ADVANCED_FEATURES.md](docs/SHEETS_ADVANCED_FEATURES.md)** - Sheets Advanced (Sprint 8)
- **[💰 BUDGET_TRACKING.md](docs/BUDGET_TRACKING.md)** - LLM Cost & Budget Management (Sprint 5)
- **[✅ FACT_CHECKING.md](docs/FACT_CHECKING.md)** - Multi-source Fact Verification

### Quick References
- **Backend API**: http://localhost:8000/docs (Swagger UI)
- **LangFuse Dashboard**: https://cloud.langfuse.com

---

## 🤝 Contributing

기여를 환영합니다! 먼저 프로젝트 전반 가이드는 [CONTRIBUTING.md](CONTRIBUTING.md)를, 에이전트 워크플로와 협업 규칙은 [AGENTS.md](docs/AGENTS.md)를 참고하세요.

### Development Flow

```bash
# 1. Fork the repository
# 2. Create feature branch
git checkout -b feature/amazing-feature

# 3. Make changes and commit
git commit -m "feat: Add amazing feature"

# 4. Push to your fork
git push origin feature/amazing-feature

# 5. Open Pull Request
```

### Code Quality

```bash
# Backend
black app/
isort app/
flake8 app/
pytest tests/ --cov=app

# Desktop
npm run lint
npm run format
npm test
```

📋 **PR Template**: See [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Fast, modern Python web framework
- [LangChain](https://python.langchain.com/) - Powerful agent framework
- [LangFuse](https://langfuse.com/) - LLM observability platform
- [Tauri](https://tauri.app/) - Secure desktop applications
- [Flutter](https://flutter.dev/) - Beautiful mobile UIs
- [Google Workspace APIs](https://developers.google.com/workspace) - Document integration
- [OpenAI](https://openai.com/) / [Anthropic](https://anthropic.com/) - LLM capabilities

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/choibongseok/my-superagent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/choibongseok/my-superagent/discussions)
- **Documentation**: [docs/](docs/)

---

<div align="center">

**Built with ❤️ by the AgentHQ Team**

⭐️ Star us on GitHub if you find this project useful!

[Report Bug](https://github.com/choibongseok/my-superagent/issues) · [Request Feature](https://github.com/choibongseok/my-superagent/issues) · [Documentation](docs/)

</div>
