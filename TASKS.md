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

## 🔴 즉시 (P4 - 통합 & 최적화)

- [ ] **Google Drive 웹훅** — Google Drive 변경 감지 자동화
  - `backend/app/api/v1/webhooks.py` 생성
  - Drive API push notifications 구현
  - 파일 업로드 → 자동 요약 트리거

- [ ] **E2E 테스트 커버리지** — 통합 테스트 확대
  - `backend/tests/e2e/` 디렉토리 생성
  - Auth flow E2E 테스트
  - Task creation → execution → completion 시나리오
  - 목표: 80% 이상 커버리지

- [ ] **API 문서 자동화** — OpenAPI/Swagger 문서 정리
  - `/openapi.json` export 검증
  - Swagger UI 개선
  - 모든 엔드포인트에 description/examples 추가

## 🟡 다음 (P5 - 고급 기능)

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
