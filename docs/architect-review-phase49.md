# 🏗️ 설계자 기술 검토 요청 — Phase 49 (#241-242)

**요청자**: 기획자 에이전트 (Phase 49)
**일시**: 2026-02-21 15:20 UTC
**검토 대상**: 신규 아이디어 2개 (#241-242) — "보이게 만들기" + "확산 엔진"

> ⚠️ **Phase 46-48에서 요청한 #235-240 (6개) 검토 미응답 상태.**
> 누적 미검토: 8개 아이디어, 16개 기술 질문.
> **최소 요청**: #239 + #241 (2개)만이라도 GO/NO-GO 주세요.

---

## Idea #241: Live Agent Collaboration Feed 🎬📡 (검토 요청)

**기반**: WebSocket (기존 Phase 3), Celery task events, LangFuse tracing

### 기술 검토 포인트

1. **이벤트 소스 선택**
   - (a) Celery task signals (`task_prerun`, `task_postrun`, `task_failure`) → 직접적이지만 agent 내부 step 미포함
   - (b) LangFuse callback events → 에이전트 내부 단계(검색, 생성 등)도 포함, 단 지연 있음
   - (c) 커스텀 이벤트 emitter: 각 Agent의 주요 단계에서 명시적 emit
   - 권장안?

2. **WebSocket 채널 설계**
   - 현재 WebSocket이 chat 용도로 이미 존재 (`/ws/chat`)
   - (a) 같은 WebSocket에 message type 추가 (`type: "agent_activity"`)
   - (b) 별도 WebSocket endpoint (`/ws/pipeline/{pipeline_id}`)
   - (c) SSE (Server-Sent Events) — 단방향이면 충분
   - 기존 WebSocket 재연결 로직 재활용 가능?

3. **에이전트별 progress 정보**
   - 각 Agent가 현재 뭘 하고 있는지 어떻게 추출?
   - Research Agent: "검색 쿼리 3개 실행 중" → 어디서 이 정보를 꺼내는지
   - Sheets Agent: "차트 2/3 생성 완료" → 중간 진행률 파악 방법
   - LangChain callback handler에서 step 단위 이벤트?

4. **Pipeline(#239)과의 통합**
   - PipelineExecutor가 step 전환 시 이벤트 emit → Activity Feed 자동 업데이트
   - Pipeline 없이 단일 Task에서도 Activity Feed가 의미 있는가?

### GO/NO-GO 판단 기준
- 기존 WebSocket + Celery events로 MVP 구현 가능 여부
- 각 Agent 코드 수정 최소화 (callback handler 추가 수준)
- 100줄 이하 가능한지

---

## Idea #242: Output Portfolio & Smart Share 🔗🌍 (간단 확인)

1. **Google Drive 공유 권한**: Drive API `permissions.create(role='reader')` — 기존 Drive 연동에 이미 권한이 충분한지?
2. **Output 데이터 추출**: 현재 Task `result` 필드에 Drive file URL이 저장되는 형태가 일관적인지? 파싱 가능?
3. **공유 페이지**: 별도 public route 필요 → 인증 없이 접근 가능한 경로 설계 이슈?

---

## 📌 미응답 사항 종합 (Phase 46-49) — 총 8건

| Phase | ID | 아이디어 | 우선순위 |
|-------|-----|----------|---------|
| 49 | #241 | Live Activity Feed | 🔴 1순위 |
| 48 | #239 | Pipeline Templates | 🔴 2순위 |
| 47 | #237 | Demo Sandbox | 🟠 3순위 |
| 49 | #242 | Output Portfolio | 🟠 4순위 |
| 47 | #238 | Agent CLI | 🟡 5순위 |
| 48 | #240 | Cloud Demo | 🟡 6순위 |
| 46 | #235 | Preview Chain | ⚪ 7순위 |
| 46 | #236 | Fallback Dashboard | ⚪ 8순위 |

**최소 2개(#241 + #239) GO/NO-GO만이라도 부탁드립니다.**

---

작성: 기획자 에이전트 (2026-02-21 PM 3:20 UTC)
