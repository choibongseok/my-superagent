# my-superagent 작업 목록

> 마지막 업데이트: 2026-02-24
> 담당: superagent-developer

## ✅ 완료 (P1-P3)

- [x] **Google OAuth 로그인** — `backend/app/api/v1/auth.py` 완전 구현
  - Google OAuth 2.0 flow, JWT 토큰, 모바일/게스트 인증
  
- [x] **Claude API 연동** — `backend/app/agents/base.py` 완성
  - `ChatAnthropic` 기본 LLM, multi-model fallback (#232)
  
- [x] **기본 태스크 API** — `backend/app/api/v1/tasks.py` 완전 구현
  - POST/GET tasks, preview, reliability gate, recovery deck
  
- [x] **Google Docs 에이전트** — `backend/app/agents/docs_agent.py` 완성
  - 문서 생성/편집, research integration, outline extraction
  
- [x] **Google Sheets 에이전트** — `backend/app/agents/sheets_agent.py` 완성
  - 스프레드시트 읽기/쓰기/분석, 차트 생성
  
- [x] **Google Slides 에이전트** — `backend/app/agents/slides_agent.py` 완성
  - 프레젠테이션 생성/편집
  
- [x] **멀티 에이전트 오케스트레이션** — `backend/app/agents/orchestrator.py` 완성
  - Docs + Sheets + Slides 협업
  
- [x] **메모리 시스템** — `backend/app/memory/` 완성
  - 대화 이력 (PostgreSQL), 벡터 검색 (pgvector), timeline API

## 🟢 완료 (P5 - 테스트 & 최적화 진행중)

- [x] **Google Drive 웹훅** — Google Drive 변경 감지 자동화 ✅
  - `backend/app/api/v1/webhooks.py` 구현 완료
  - Drive API push notifications 완전 구현
  - 파일 업로드 → 자동 요약 트리거 작동
  - **테스트**: `backend/tests/test_webhooks.py` 완성

- [🔄] **E2E 테스트 커버리지 확대** — 통합 테스트 추가 (진행중)
  - ✅ `backend/tests/test_e2e_api_flows.py` — HTTP API E2E tests 추가
  - ✅ Auth flow, Task API, Webhooks, Orchestration, Memory API 테스트
  - ✅ **DB 통합 테스트**: `backend/tests/test_db_integration.py` — 21개 테스트 추가
    - User CRUD, Task CRUD, Chat/Message 생성, 관계 테스트
    - Transaction/rollback, 제약 조건, 벌크 작업, 페이지네이션
    - 실제 DB fixture 사용 (PostgreSQL/SQLite)
  - ✅ 커버리지: 20% → 19.74% (안정화, 목표: 70%)
  - 🔄 다음: API 엔드포인트 실제 호출 테스트, Agent 실행 E2E

- [ ] **API 문서 자동화** — OpenAPI/Swagger 문서 정리
  - `/openapi.json` export 검증
  - Swagger UI 개선
  - 모든 엔드포인트에 description/examples 추가

## 🟡 다음 (P5 - 테스트 & 문서화)

### 🔴 우선순위 1: E2E 테스트 커버리지 확대 (21% → 70%)

- [ ] **Agent 실행 E2E 테스트** (고우선순위)
  - 파일: `backend/tests/test_agent_e2e.py` (신규 생성)
  - 테스트 대상:
    - `DocsAgent.run()` — 실제 Google Docs 생성/편집
    - `SheetsAgent.run()` — 실제 Sheets 읽기/쓰기
    - `SlidesAgent.run()` — 실제 Slides 생성
    - `Orchestrator.execute()` — 멀티 에이전트 협업
  - Celery worker mock 또는 실제 통합
  - 완료 기준: 각 에이전트당 3개 이상 테스트, 총 12+ 테스트 추가

- [ ] **Memory System E2E 테스트**
  - 파일: `backend/tests/test_memory_e2e.py` (신규 생성)
  - 테스트 대상:
    - `MemoryManager.save_conversation()`
    - `MemoryManager.search_similar_tasks()`
    - pgvector 임베딩 검색
    - Timeline API (`GET /api/v1/memory/timeline`)
  - 완료 기준: 벡터 검색 정확도 테스트 포함, 8+ 테스트 추가

- [ ] **API 엔드포인트 통합 테스트 확장**
  - 파일: `backend/tests/test_api_v1_extended.py` (신규 생성)
  - 미커버 엔드포인트:
    - `/api/v1/tasks/{id}/retry`
    - `/api/v1/tasks/{id}/cancel`
    - `/api/v1/memory/search`
    - `/api/v1/webhooks/drive/watch`
  - 완료 기준: 15+ 엔드포인트 추가 커버, HTTP 4xx/5xx 에러 케이스 포함

- [ ] **에러 핸들링 & Edge Case 테스트**
  - 파일: `backend/tests/test_error_handling.py` (신규 생성)
  - 테스트 시나리오:
    - Google API rate limit 처리
    - Invalid OAuth token 처리
    - Network timeout 시뮬레이션
    - DB connection pool exhaustion
  - 완료 기준: 10+ failure scenario 테스트

### 🔴 우선순위 2: API 문서 자동화

- [ ] **OpenAPI 스펙 검증 & 개선**
  - 파일: `backend/app/main.py` 수정
  - 작업:
    - FastAPI `openapi_schema` 커스터마이징
    - 모든 엔드포인트에 `summary`, `description`, `response_model` 추가
    - Example 데이터 추가 (`openapi_examples`)
  - 엔드포인트: `GET /openapi.json` export 검증
  - 완료 기준: `/openapi.json` 다운로드 → Swagger Editor 검증 통과

- [ ] **Swagger UI 개선**
  - 파일: `backend/app/main.py` 수정
  - 작업:
    - Swagger UI 테마 커스터마이징
    - Try-it-out 기본 활성화
    - Authentication UI 개선 (JWT bearer)
  - 완료 기준: `/docs` 접속 시 professional UI 확인

- [ ] **API 문서 페이지 작성**
  - 파일: `docs/API.md` (신규 생성)
  - 내용:
    - 인증 플로우 설명
    - 주요 엔드포인트 사용 예제
    - Rate limiting, pagination 가이드
    - Webhook 설정 가이드
  - 완료 기준: 외부 개발자가 문서만으로 통합 가능한 수준

## 🟢 이후 (P5 - 고급 기능)

- [ ] **멀티 테넌시** — 조직/팀 단위 관리
  - Organization model 추가
  - Team-based access control
  - Workspace 개념 도입

- [ ] **비용 추적** — LLM 사용량 모니터링
  - Token usage tracking per task
  - Cost estimation API
  - Budget alerts

- [ ] **스케줄링** — 주기적 태스크 실행
  - Cron-style task scheduling
  - Recurring document generation

## 🟢 이후 (P6 - 확장)

- [ ] **플러그인 시스템** — 외부 도구 통합
  - Notion, Jira, Confluence 연동
  - 커스텀 에이전트 플러그인 API

- [ ] **FactoryHub 통합 준비** (선택적)
  - OpenAPI manifest 작성
  - 외부 시스템 호출 인터페이스 정리

---

## 🎯 현재 우선순위

1. **Google Drive 웹훅** - 자동화의 핵심
2. **E2E 테스트** - 안정성 확보
3. **API 문서화** - 외부 통합 준비
