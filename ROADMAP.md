# my-superagent 로드맵

> 전략: Google Workspace AI 자동화 플랫폼 → 최종 FactoryHub 앱으로 흡수

## ✅ 완료
- [x] FastAPI 백엔드 구조 (agent, task, api 레이어)
- [x] LangChain 에이전트 기반 아키텍처
- [x] Celery 비동기 태스크 처리
- [x] PostgreSQL + Redis 인프라

## ✅ Phase 1 — 기본 동작 (완료)

### P1-A: Google OAuth 로그인 ✅
- [x] `/api/v1/auth/login` → Google OAuth redirect URL 반환
- [x] `/api/v1/auth/callback` → code 교환 → JWT 발급
- [x] 로그인 후 Google API credentials 저장 (DB)
- [x] 모바일/게스트 인증 엔드포인트 추가
- [x] `backend/app/api/v1/auth.py` 완성

### P1-B: Anthropic Claude API 연동 ✅
- [x] `base.py`에서 `ChatAnthropic` 사용
- [x] Multi-model fallback 지원 (#232)
- [x] `ANTHROPIC_API_KEY` 환경변수 연동
- [x] OpenAI와 Anthropic 동시 지원

### P1-C: 기본 태스크 API ✅
- [x] `POST /api/v1/tasks` — 태스크 생성 (agent_type, prompt, user_id)
- [x] `GET /api/v1/tasks/{id}` — 태스크 상태 조회
- [x] `GET /api/v1/tasks` — 내 태스크 목록
- [x] Celery로 비동기 처리, 상태: pending/running/done/failed
- [x] Task preview, reliability gate, recovery deck 추가

## ✅ Phase 2 — Google Workspace 에이전트 (완료)

### P2-A: Google Docs 에이전트 ✅
- [x] `docs_agent.py` 완성 — 문서 생성/편집/요약
- [x] Research integration (ResearchAgent 활용)
- [x] Outline extraction + content metrics
- [x] Citation management

### P2-B: Google Sheets 에이전트 ✅
- [x] `sheets_agent.py` 완성 — 스프레드시트 읽기/쓰기/분석
- [x] Data analysis capabilities
- [x] Chart/visualization tools

### P2-C: Google Slides 에이전트 ✅
- [x] `slides_agent.py` 완성 — 프레젠테이션 생성/편집
- [x] Template-based slide generation

### P2-D: 멀티 에이전트 오케스트레이션 ✅
- [x] `orchestrator.py` 완성 — Docs + Sheets + Slides 협업
- [x] Multi-agent task routing
- [x] `POST /api/v1/orchestrate` 엔드포인트

## ✅ Phase 3 — 고도화 (완료)

### P3-A: 메모리 시스템 ✅
- [x] 대화 이력 저장 (PostgreSQL)
- [x] 벡터 검색 (pgvector) — 과거 태스크 유사 검색
- [x] MemoryManager (conversation + vector memory)
- [x] Memory timeline API (#243)
- [x] Semantic search endpoint

### P3-B: 웹훅 & 알림 ✅
- [x] WebSocket 실시간 업데이트
- [x] Slack 알림 플러그인
- [x] Google Drive 변경 감지 웹훅
- [x] 자동 트리거 (새 파일 업로드 → 자동 요약)

## 🏁 Phase 4 — FactoryHub 흡수 준비
- [x] OpenAPI 스펙 정리 (`/openapi.json` export) — ✅ 완료 (2026-02-24)
- [ ] FactoryHub manifest `manifests/ai-agent.json` 작성
- [ ] FactoryHub Go 코드에서 my-superagent API 호출
- [ ] FactoryHub 이벤트 수신 엔드포인트 (`/api/v1/factoryhub/callback`)

## 💡 Phase 5 — 아키텍처 고도화 (신규)

### P5-A: 마이크로서비스 전환 준비
- [ ] **서비스 분리 설계**
  - Auth Service (독립 인증 서버)
  - Agent Service (LLM 처리 전용)
  - Task Service (작업 관리 전용)
  - Gateway API (통합 라우터)
  
- [ ] **gRPC API 추가**
  - FactoryHub Go 백엔드와 고성능 통신
  - Protocol Buffers 스키마 정의 (`proto/agent.proto`)
  - Bi-directional streaming 지원 (실시간 진행 상태)
  
- [ ] **이벤트 기반 아키텍처**
  - RabbitMQ 또는 Kafka 도입 검토
  - Event-driven task execution
  - 비동기 알림 시스템 (Webhook → Event Bus)

### P5-B: 엔터프라이즈 기능
- [ ] **멀티 테넌시** (Organization/Workspace 개념)
  - Organization model + RBAC
  - Per-tenant 리소스 격리
  - Billing/quota 관리
  
- [ ] **감사 로그 (Audit Trail)**
  - 모든 API 호출 기록
  - 데이터 변경 이력 추적
  - Compliance 대응 (GDPR, SOC2)
  
- [ ] **LLM 비용 최적화**
  - Token usage analytics dashboard
  - Model routing (cheap vs expensive models)
  - Caching layer (semantic deduplication)

### P5-C: AI 고도화
- [ ] **Multi-modal 지원**
  - 이미지 분석 (Google Vision API)
  - 음성 → 텍스트 (Whisper API)
  - 동영상 자막 생성
  
- [ ] **RAG (Retrieval-Augmented Generation)**
  - 사용자별 knowledge base
  - Pinecone 또는 Weaviate 통합
  - 문서 자동 임베딩
  
- [ ] **Agent Fine-tuning**
  - 사용자 피드백 기반 모델 학습
  - Few-shot learning examples 축적
  - Custom prompt templates per user

## 💡 Phase 6 — 엔터프라이즈 & 확장 (신규)

### P6-A: Real-time Collaboration
- [ ] **WebSocket 고도화**
  - Multi-user document editing (Google Docs-style)
  - Live cursor tracking
  - Real-time comment threads
  
- [ ] **Agent-to-Agent 통신**
  - Inter-agent messaging protocol
  - Shared memory pool (distributed cache)
  - Collaborative task execution

### P6-B: Advanced Analytics & Monitoring
- [ ] **Dashboard 개선**
  - Token usage visualization (daily/monthly trends)
  - Agent performance metrics (success rate, latency)
  - User engagement analytics
  
- [ ] **Observability**
  - OpenTelemetry 통합
  - Distributed tracing (Jaeger/Zipkin)
  - Custom metrics (Prometheus)

### P6-C: Mobile & Cross-platform SDK
- [ ] **Mobile SDK**
  - iOS SDK (Swift)
  - Android SDK (Kotlin)
  - React Native wrapper
  
- [ ] **Multi-platform 배포**
  - Desktop app (Tauri — 이미 있음)
  - Browser extension (Chrome/Firefox)
  - CLI tool (Python/Go)

### P6-D: Plugin Marketplace & Ecosystem
- [ ] **Plugin SDK**
  - Custom agent plugin API
  - Third-party tool integrations (Notion, Jira, Confluence)
  - Community-contributed agents
  
- [ ] **Marketplace 플랫폼**
  - Plugin discovery & installation
  - Revenue sharing model
  - Security scanning & approval

### P6-E: Global Infrastructure
- [ ] **Multi-region 배포**
  - US, EU, APAC regions
  - Data residency compliance (GDPR, SOC2)
  - CDN integration (CloudFront/Fastly)
  
- [ ] **High Availability**
  - Load balancing (HAProxy/Nginx)
  - Auto-scaling (Kubernetes HPA)
  - Disaster recovery plan

---

## 🎯 2026 전략 로드맵

**Q1 2026 (현재)**
- ✅ Phase 1-3 완료 (Core 기능)
- 🔄 Phase 4-5 진행 중 (FactoryHub 통합, 고도화)
- 🎯 목표: 테스트 커버리지 70%, API 문서화

**Q2 2026**
- 🚀 Phase 5 완료 (Multi-tenancy, Cost tracking, Scheduling)
- 🎯 목표: FactoryHub 통합 완료, 프로덕션 배포

**Q3 2026**
- 🌐 Phase 6 시작 (Real-time collaboration, Advanced analytics)
- 🎯 목표: Mobile SDK 베타, Plugin marketplace 런칭

**Q4 2026**
- 🌍 Global expansion (Multi-region, High availability)
- 🎯 목표: 엔터프라이즈 고객 확보, SOC2 인증
