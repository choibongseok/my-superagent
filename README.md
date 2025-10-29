# 🚀 AgentHQ - Multi-Client AI Super Agent Hub

> **An intelligent agent system that creates Google Docs, Sheets, and Slides through natural language commands**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![Tauri](https://img.shields.io/badge/Tauri-1.5+-orange.svg)](https://tauri.app/)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-blue.svg)](https://flutter.dev/)

---

## 🌟 Overview

**AgentHQ** is a cross-platform AI agent system that allows users to:

- 📊 Generate data-driven **Google Sheets** from natural language
- 📝 Create comprehensive **Google Docs** reports with citations
- 🎨 Design professional **Google Slides** presentations
- 🔍 Perform intelligent web research and analysis
- 🧠 Maintain conversation memory for contextual interactions
- 🤝 Seamless Google Workspace integration

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
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL + PGVector
- **LLM**: OpenAI GPT-4 / Anthropic Claude
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
# Edit .env with your Google OAuth credentials

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
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://user:pass@localhost:5432/agenthq
REDIS_URL=redis://localhost:6379/0
```

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

## 🎯 Roadmap

### Phase 1: MVP (Week 1-2) ✅
- [x] Backend API foundation
- [x] Google OAuth integration
- [x] Tauri desktop UI
- [x] Basic task queue
- [x] Docs/Sheets/Slides generation

### Phase 2: Intelligence (Week 3-4)
- [ ] Web research agent
- [ ] Memory & context system
- [ ] Multi-turn conversations
- [ ] Source citation
- [ ] Template system

### Phase 3: Mobile (Week 5-6)
- [ ] Flutter UI implementation
- [ ] Mobile OAuth flow
- [ ] Push notifications
- [ ] Offline mode
- [ ] File caching

### Phase 4: Collaboration (Week 7-8)
- [ ] Google Workspace integration
- [ ] Team sharing
- [ ] Permission management
- [ ] Real-time sync
- [ ] Activity logs

### Phase 5: Scale (Week 9-10)
- [ ] Performance optimization
- [ ] Advanced caching
- [ ] Rate limiting
- [ ] Usage analytics
- [ ] Enterprise features

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
- [Tauri](https://tauri.app/) for secure desktop applications
- [Flutter](https://flutter.dev/) for beautiful mobile UIs
- [Google Workspace APIs](https://developers.google.com/workspace) for document integration
- [OpenAI](https://openai.com/) / [Anthropic](https://anthropic.com/) for LLM capabilities

---

## 📞 Support

- 📧 Email: support@agenthq.example.com
- 💬 Discord: [Join our community](https://discord.gg/agenthq)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/agenthq/issues)
- 📖 Docs: [Documentation](https://docs.agenthq.example.com)

---

**Built with ❤️ by the AgentHQ Team**

⭐️ Star us on GitHub if you find this project useful!
