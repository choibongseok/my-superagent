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

### P3-B: 웹훅 & 알림 ✅ (부분 완료)
- [x] WebSocket 실시간 업데이트
- [x] Slack 알림 플러그인
- [ ] Google Drive 변경 감지 웹훅 (TODO)
- [ ] 자동 트리거 (새 파일 업로드 → 자동 요약) (TODO)

## 🏁 Phase 4 — FactoryHub 흡수
- [ ] OpenAPI 스펙 정리 (`/openapi.json` export)
- [ ] FactoryHub manifest `manifests/ai-agent.json` 작성
- [ ] FactoryHub Go 코드에서 my-superagent API 호출
