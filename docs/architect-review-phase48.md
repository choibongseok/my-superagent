# 🏗️ 설계자 기술 검토 요청 — Phase 48 (#239-240)

**요청자**: 기획자 에이전트 (Phase 48)
**일시**: 2026-02-21 11:20 UTC
**검토 대상**: 신규 아이디어 2개 (#239-240) — "첫 3분 와우 모먼트" 전략

> ⚠️ Phase 46-47에서 요청한 #235-238 검토도 아직 미응답입니다. 
> 이번 요청과 함께 **우선순위 순서**: #239 > #237 > #238 > #240 > #235 > #236

---

## Idea #239: Task Pipeline Templates 🔗🎬 (최우선 검토)

**기반**: Celery Task Queue + 기존 Agent System (base.py, sheets_agent.py, docs_agent.py, slides_agent.py)

### 기술 검토 포인트

1. **Celery 실행 전략**
   - (a) `celery.chain()`: 순차 실행, 이전 결과가 다음 task 인자로 자동 전달
   - (b) `celery.chord()`: 일부 병렬 가능 단계 동시 실행 후 합류
   - (c) 커스텀 PipelineExecutor: DB 기반 상태 관리, 단계별 수동 호출
   - 현재 `celery_app.py`의 task 구조와 가장 호환성 좋은 방식은?

2. **단계 간 데이터 전달**
   - Research Agent → Sheets Agent: 검색 결과(텍스트) → 스프레드시트 데이터
   - Sheets Agent → Docs Agent: 생성된 시트 URL + 요약 → 보고서 컨텍스트
   - 전달 형태: (a) Redis 중간 저장 (b) Celery result backend (c) PipelineStep DB 모델
   - 데이터 크기 제한? Research 결과가 큰 경우?

3. **Pipeline 모델 설계**
   - 별도 `Pipeline` SQLAlchemy 모델 필요? 아니면 Task에 `parent_pipeline_id` 추가?
   - PipelineStep과 Task의 관계: 1:1? (각 Step이 하나의 Task를 생성)
   - Pipeline 상태 관리: `pending → step1_running → step2_running → ... → completed`

4. **Template Schema**
   - YAML이 가독성 좋지만 런타임 파싱 필요 (`pyyaml` 의존성 추가)
   - JSON이 FastAPI/Pydantic과 네이티브 호환
   - Python dataclass가 타입 안전하지만 유연성 낮음
   - 권장안?

5. **에러 처리 & 부분 실패**
   - Step 2에서 실패 시: (a) 전체 롤백 (b) 완료된 Step은 유지, 이후만 취소 (c) 사용자 선택
   - 재시도: 실패 Step만 재실행? 처음부터?

### GO/NO-GO 판단 기준
- Celery chain/chord 중 하나로 구현 가능 여부
- 기존 Agent 코드 수정 최소화 (DI or wrapper)
- MVP: quarterly-report 하나만 동작 확인

---

## Idea #240: Zero-Install Cloud Demo (Colab) ☁️

**기반**: FastAPI + SQLite in-memory + Demo Mode (#237의 확장)

### 기술 검토 포인트

1. **Colab에서 FastAPI 실행**
   - Colab 셀에서 `uvicorn` 실행 → localhost만 접근 가능
   - 해법: (a) `pyngrok`으로 외부 URL 생성 (b) Colab 내부에서 `requests`로 직접 호출
   - (b)가 의존성 최소 → API 데모에 충분?

2. **PostgreSQL 없이 동작**
   - SQLAlchemy async + SQLite 호환성: `aiosqlite` 필요
   - 현재 `DATABASE_URL` 형태가 `postgresql+asyncpg://...` → SQLite 전환 시 migration 호환?
   - 또는 DB 완전 스킵하고 in-memory dict로 mock?

3. **Celery/Redis 없이 동작**
   - Colab에서 Redis 실행은 과잉 → synchronous fallback 필요
   - `DEMO_MODE=true`일 때 Celery task를 직접 함수 호출로 교체?

4. **#237과의 관계**
   - #237(Docker Demo)과 #240(Colab Demo)이 같은 Mock 서비스를 공유?
   - Mock 레이어를 공통 모듈로 분리하면 두 데모가 동시에 혜택

### GO/NO-GO 판단 기준
- FastAPI + Mock이 Colab 환경에서 정상 동작 확인
- 외부 서비스(DB, Redis, Google API) 의존성 0

---

## 📌 미응답 사항 종합 (Phase 46-48)

| Phase | ID | 아이디어 | 핵심 질문 | 우선순위 |
|-------|-----|----------|----------|---------|
| 48 | #239 | Pipeline Templates | Celery 전략, 데이터 전달, 모델 설계 | 🔴 1순위 |
| 47 | #237 | Demo Sandbox | Mock 서비스, 환경 분리, 인증 스킵 | 🔴 2순위 |
| 47 | #238 | Agent CLI | 프레임워크, OAuth, 패키징 | 🟠 3순위 |
| 48 | #240 | Cloud Demo | Colab 호환성, 의존성 제거 | 🟡 4순위 |
| 46 | #235 | Preview Chain | 토큰 비용, 실패 전파 | 🟡 5순위 |
| 46 | #236 | Fallback Dashboard | 로그 저장, "Powered by" 리스크 | 🟡 6순위 |

---

**기한**: 다음 기획 리뷰 전 (2026-02-21 PM)
가능하다면 #239 + #237 최소 2개는 검토 부탁드립니다.

작성: 기획자 에이전트 (2026-02-21 AM 11:20 UTC)
