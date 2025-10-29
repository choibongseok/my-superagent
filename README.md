# 🚀 AgentHQ - Multi-Client AI Super Agent Hub

> **세계 최고 수준의 Multi-Agent AI Platform - Google Workspace 자동화 시스템**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.1+-purple.svg)](https://python.langchain.com/)
[![LangFuse](https://img.shields.io/badge/LangFuse-2.6+-teal.svg)](https://langfuse.com/)
[![Tauri](https://img.shields.io/badge/Tauri-1.5+-orange.svg)](https://tauri.app/)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-blue.svg)](https://flutter.dev/)

---

## 🌟 Overview

**AgentHQ**는 세계 최고 수준의 Multi-Agent AI Platform입니다.

### 🎯 핵심 기능

- 📊 **Google Sheets 자동 생성** - 자연어로 데이터 기반 스프레드시트 생성
- 📝 **Google Docs 리포트 작성** - 인용 출처가 포함된 종합 문서 작성
- 🎨 **Google Slides 프레젠테이션** - 전문적인 슬라이드 자동 디자인
- 🔍 **지능형 웹 리서치** - 최신 정보 검색 및 분석
- 🧠 **대화 컨텍스트 기억** - 다중 턴 대화를 통한 맥락 유지
- 🤝 **Google Workspace 통합** - 완벽한 생태계 연동

### 🏆 차별화 포인트

- **🔗 LangChain 기반 Agent** - 구조화되고 확장 가능한 AI Agent 시스템
- **📊 LangFuse 모니터링** - 실시간 LLM 비용 추적 및 성능 최적화
- **🎨 Multi-Platform** - Desktop (Tauri), Mobile (Flutter), Web 지원
- **🔒 Enterprise-Grade** - 보안, 확장성, 안정성을 고려한 설계

### Multi-Platform Support

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentHQ Architecture                      │
├─────────────────┬───────────────┬───────────────┬───────────┤
│   Desktop       │   Mobile      │   Backend     │  Storage  │
│   (Tauri)       │   (Flutter)   │   (FastAPI)   │  (Google) │
├─────────────────┼───────────────┼───────────────┼───────────┤
│ • React UI      │ • iOS         │ • Auth        │ • Docs    │
│ • Native OS     │ • Android     │ • Task Queue  │ • Sheets  │
│ • OAuth         │ • OAuth       │ • Agent       │ • Slides  │
│                 │               │ • Memory      │ • Drive   │
└─────────────────┴───────────────┴───────────────┴───────────┘
```

---

## 📁 Project Structure

```
AgentHQ/
├── backend/          # FastAPI + Celery + Agent Pipeline
│   ├── app/
│   │   ├── api/      # REST endpoints
│   │   ├── core/     # Config, auth, database
│   │   ├── agents/   # LLM agent logic
│   │   ├── services/ # Google API integrations
│   │   └── models/   # SQLAlchemy models
│   └── tests/
│
├── desktop/          # Tauri + React (Primary Client)
│   ├── src/          # React components
│   ├── src-tauri/    # Rust backend
│   └── public/
│
├── mobile/           # Flutter (iOS/Android)
│   ├── lib/
│   ├── android/
│   └── ios/
│
├── infra/            # Infrastructure as Code
│   ├── docker/
│   ├── terraform/
│   └── cloudbuild/
│
└── docs/             # Documentation
    ├── api/          # OpenAPI specs
    ├── architecture/ # System design
    └── guides/       # Setup guides
```

---

## 🏗️ Tech Stack

### Backend
- **API Gateway**: FastAPI (Python 3.11+)
- **Agent Framework**: LangChain (Structured AI Agents)
- **LLM Observability**: LangFuse (Monitoring & Analytics)
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL + PGVector
- **LLM Providers**: OpenAI GPT-4 / Anthropic Claude
- **Google APIs**: Docs, Sheets, Slides, Drive

### Desktop (Primary)
- **Framework**: Tauri 1.5+
- **Frontend**: React 18 + TypeScript
- **State**: Zustand / React Query
- **UI**: Tailwind CSS + shadcn/ui

### Mobile (Extension)
- **Framework**: Flutter 3.16+
- **State**: Riverpod / Bloc
- **Auth**: google_sign_in

### Infrastructure
- **Cloud**: Google Cloud Run
- **Storage**: Google Cloud Storage
- **CDN**: Cloud CDN
- **Monitoring**: Cloud Logging + Prometheus

---

## 🚀 Quick Start

### Prerequisites

```bash
# Required
- Node.js 18+
- Python 3.11+
- Rust 1.70+ (for Tauri)
- Flutter 3.16+ (for mobile)
- Docker & Docker Compose
- Google Cloud CLI

# Optional
- PostgreSQL 15+
- Redis 7+
```

### 1️⃣ Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your credentials:
# - Google OAuth (Client ID, Secret)
# - LangFuse API Keys (Public Key, Secret Key)
# - OpenAI/Anthropic API Keys

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

### 2️⃣ Desktop (Tauri) Setup

```bash
cd desktop

# Install dependencies
npm install

# Run development mode
npm run tauri dev

# Build production
npm run tauri build
```

### 3️⃣ Mobile (Flutter) Setup

```bash
cd mobile

# Get dependencies
flutter pub get

# Run on device/emulator
flutter run

# Build APK (Android)
flutter build apk --release

# Build IPA (iOS)
flutter build ios --release
```

---

## 🔑 Google OAuth Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project: **AgentHQ**
3. Enable APIs:
   - Google Docs API
   - Google Sheets API
   - Google Slides API
   - Google Drive API

### 2. Configure OAuth Consent Screen

```
Application name: AgentHQ
User support email: your-email@example.com
Scopes:
  - .../auth/documents
  - .../auth/spreadsheets
  - .../auth/presentations
  - .../auth/drive.file
```

### 3. Create OAuth 2.0 Credentials

**Desktop (Tauri)**:
- Application type: Desktop app
- Download JSON → Save as `backend/credentials.json`

**Mobile (Flutter)**:
- Application type: iOS / Android
- Configure package name/bundle ID
- Add SHA-1 fingerprint (Android)

### 4. Environment Variables

```bash
# backend/.env

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# LangFuse (LLM Observability)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Database & Cache
DATABASE_URL=postgresql://user:pass@localhost:5432/agenthq
REDIS_URL=redis://localhost:6379/0

# App Settings
DEBUG=true
LOG_LEVEL=INFO
```

> 💡 **LangFuse 설정 방법**: [docs/LANGFUSE_SETUP.md](docs/LANGFUSE_SETUP.md) 참조

---

## 📖 API Documentation

### Core Endpoints

```http
POST   /api/v1/tasks              # Create new task
GET    /api/v1/tasks/{id}         # Get task status
GET    /api/v1/tasks/{id}/result  # Get task result (Google links)
DELETE /api/v1/tasks/{id}         # Cancel task

GET    /api/v1/auth/google        # Initiate OAuth flow
GET    /api/v1/auth/callback      # OAuth callback
POST   /api/v1/auth/refresh       # Refresh access token

GET    /api/v1/memory             # Get conversation history
POST   /api/v1/memory             # Save memory
DELETE /api/v1/memory/{id}        # Clear memory
```

### Example Usage

```bash
# Create a task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a quarterly sales report for Q4 2024",
    "output_type": "docs"
  }'

# Response
{
  "task_id": "uuid-here",
  "status": "pending",
  "created_at": "2024-10-29T00:00:00Z"
}

# Check status
curl http://localhost:8000/api/v1/tasks/uuid-here \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "task_id": "uuid-here",
  "status": "completed",
  "result": {
    "doc_url": "https://docs.google.com/document/d/...",
    "created_at": "2024-10-29T00:01:30Z"
  }
}
```

---

## 🧪 Development

### Run Tests

```bash
# Backend
cd backend
pytest tests/ -v --cov=app

# Desktop
cd desktop
npm test

# Mobile
cd mobile
flutter test
```

### Code Quality

```bash
# Backend
black app/
isort app/
flake8 app/
mypy app/

# Desktop
npm run lint
npm run format

# Mobile
flutter analyze
flutter format .
```

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

# Build for all platforms
npm run tauri build

# Binaries will be in:
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

## 🎯 Development Plan

**📋 세부 개발 계획은 다음 문서를 참고하세요:**

- **[📊 PHASE_PLAN.md](docs/PHASE_PLAN.md)** - 전체 로드맵 및 페이즈별 상세 계획 (Phase 0-6)
- **[🔧 PHASE_0_IMPLEMENTATION.md](docs/PHASE_0_IMPLEMENTATION.md)** - Phase 0 실행 가이드 (LangChain/LangFuse 통합)
- **[🔗 LANGCHAIN_GUIDE.md](docs/LANGCHAIN_GUIDE.md)** - LangChain 완전 가이드
- **[📊 LANGFUSE_SETUP.md](docs/LANGFUSE_SETUP.md)** - LangFuse 설정 및 활용 가이드

### Current Status (2024-10-29)

**✅ Completed (Phase 1 - MVP)**
- Backend API foundation (FastAPI)
- Google OAuth integration
- Tauri desktop UI structure
- Basic task queue (Celery + Redis)
- Database models (PostgreSQL + PGVector)

**🔄 In Progress (Phase 0 - Foundation Enhancement)**
- LangChain integration for structured AI agents
- LangFuse integration for LLM observability
- Prompt management system
- Comprehensive testing (target: 80%+ coverage)

**📍 Next Steps**
1. **Week 1-2**: Complete Phase 0 (LangChain/LangFuse integration)
2. **Week 3-4**: Phase 1 (Core Agent implementation)
3. **Week 5-6**: Phase 2 (Intelligence & Memory)

> 💡 **자세한 내용은 [docs/PHASE_PLAN.md](docs/PHASE_PLAN.md)를 참조하세요.**

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Development Flow

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) for the amazing Python framework
- [LangChain](https://python.langchain.com/) for the powerful agent framework
- [LangFuse](https://langfuse.com/) for LLM observability and analytics
- [Tauri](https://tauri.app/) for secure desktop applications
- [Flutter](https://flutter.dev/) for beautiful mobile UIs
- [Google Workspace APIs](https://developers.google.com/workspace) for document integration
- [OpenAI](https://openai.com/) / [Anthropic](https://anthropic.com/) for LLM capabilities

---

## 📖 Documentation

### Architecture & Planning
- **[🏗️ ARCHITECTURE.md](docs/ARCHITECTURE.md)** - 시스템 아키텍처 상세 설계
- **[📊 PHASE_PLAN.md](docs/PHASE_PLAN.md)** - 전체 개발 로드맵 (Phase 0-6)
- **[📝 OAUTH_SETUP.md](docs/OAUTH_SETUP.md)** - Google OAuth 설정 가이드

### Implementation Guides
- **[🔧 PHASE_0_IMPLEMENTATION.md](docs/PHASE_0_IMPLEMENTATION.md)** - Phase 0 실행 가이드
- **[🔗 LANGCHAIN_GUIDE.md](docs/LANGCHAIN_GUIDE.md)** - LangChain 개념 및 구현 패턴
- **[📊 LANGFUSE_SETUP.md](docs/LANGFUSE_SETUP.md)** - LangFuse 모니터링 시스템 구축

### Quick References
- **Backend API**: http://localhost:8000/docs (FastAPI Swagger UI)
- **LangFuse Dashboard**: https://cloud.langfuse.com (LLM Observability)
- **Architecture Diagram**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 📞 Support

- 📧 Email: support@agenthq.example.com
- 💬 Discord: [Join our community](https://discord.gg/agenthq)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/agenthq/issues)
- 📚 Documentation: [docs/](docs/)

---

**Built with ❤️ by the AgentHQ Team**

⭐️ Star us on GitHub if you find this project useful!
