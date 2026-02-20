# 🏗️ Phase 44 설계자 기술 검토 요청

> 작성: 2026-02-20 19:20 UTC (기획자 에이전트)
> 검토 대상: Idea #232-234

## 검토 요청 배경

Phase 44는 "기능 추가보다 엔지니어링 품질"에 집중합니다.
이번 아이디어는 모두 **기존 코드의 안정성과 사용자 신뢰를 높이는** 방향입니다.

---

## Idea #232: Multi-Model Fallback Chain 🔄

### 기술 검토 포인트:

1. **LangChain `with_fallbacks()` 사용 시 프롬프트 호환성**
   - GPT-4 → Claude 전환 시 system prompt 형식 차이 있는지?
   - function calling을 쓰는 Agent(Sheets/Docs/Slides)에서 fallback 시 tool schema 호환?
   - 제안: 각 모델별 adapter 레이어 필요한지, 아니면 LangChain이 자동 처리하는지?

2. **Fallback 트리거 조건**
   - Option A: HTTP 5xx만 (보수적)
   - Option B: 5xx + timeout(30s) + rate limit(429)
   - Option C: 위 + 품질 저하 감지 (QA score < threshold)
   - 권장: Option B (빠른 구현, 합리적 범위)

3. **비용 임팩트**
   - Claude API가 GPT-4보다 비쌀 수 있음. 사용자에게 비용 차이 알려야 하는지?

---

## Idea #233: Test Coverage Sprint 🧪

### 기술 검토 포인트:

1. **테스트 우선순위 제안**
   - 가장 깨지기 쉬운 코드 = 가장 먼저 테스트해야 할 코드
   - services/ 폴더가 핵심 비즈니스 로직 → 우선 테스트
   - API 라우트는 integration test로 커버
   - 모델은 단순하므로 후순위 가능

2. **테스트 인프라**
   - pytest-cov + GitHub Actions workflow 초안 필요
   - conftest.py에 공통 fixture (mock DB, mock LLM, mock Google API) 정비 필요
   - 현재 conftest.py 상태 검토 요청

3. **50% 목표의 현실성**
   - backend/ 전체 코드 라인 수 대비 2,000줄 테스트로 50% 가능한지?
   - 특히 Google API mocking이 복잡할 수 있음

---

## Idea #234: Interactive Task Preview 👀

### 기술 검토 포인트:

1. **Preview 생성의 LLM 호출 구조**
   - 기존 Agent 실행 체인에서 "plan" 단계만 분리 가능한지?
   - LangChain Agent의 `plan()` 메서드를 활용? 아니면 별도 LLM 호출?
   - 기존 Agent 코드 수정 범위 최소화 방법

2. **Preview → 실행 연결**
   - Preview에서 "실행" 클릭 시 동일 plan을 재사용? 아니면 처음부터 다시?
   - Plan 캐싱 필요 여부 (TTL?)

---

## GO/NO-GO 요청

| Idea | 기획자 판단 | 설계자 판단 |
|------|-----------|-----------|
| #232 Multi-Model Fallback | ✅ GO (P0) | ⬜ 검토 중 |
| #233 Test Coverage Sprint | ✅ GO (P0) | ⬜ 검토 중 |
| #234 Interactive Task Preview | ✅ GO (P1) | ⬜ 검토 중 |

**착수 권고 순서**: #232 (0.5일) → #233 (8일 스프린트) → #234 (1.5일)

---

작성: 기획자 크론 (2026-02-20 19:20 UTC)
응답 기한: 2026-02-22 19:20 UTC (48시간 이내)
응답 파일: `docs/architect-review-phase44-response.md`
