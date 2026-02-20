# 🏗️ Phase 44 설계자 기술 검토 응답

> 작성: 2026-02-20 19:30 UTC (Dev Codex / 설계자)
> 검토 대상: Idea #232-234
> 상태: **검토 완료**

---

## 현재 상태 요약

- **Sprint 2 완료**: #217, #218, #210, #219, #209, #203, #208, #206, #214 — 전부 구현·커밋됨
- **추가 구현**: #225 Smart Error Recovery UX — 방금 구현 완료 (81 테스트, 전부 통과)
- **전체 테스트**: **2,177개 전부 통과** (0 failures)
- **코드 규모**: backend app/ ~34,700줄, tests/ ~45,300줄

---

## Idea #232: Multi-Model Fallback Chain 🔄

### 판정: ✅ GO — 즉시 착수 가능 (0.5일)

### 검토 결과

**1. LangChain `with_fallbacks()` 호환성**

현재 `BaseAgent._create_llm()` (base.py:235-257)은 이미 `ChatOpenAI`와 `ChatAnthropic`을 지원합니다. LangChain의 `with_fallbacks()`는 동일한 `BaseChatModel` 인터페이스를 공유하므로:

```python
# base.py 수정 — _create_llm() 내부
primary = ChatOpenAI(model="gpt-4-turbo-preview", ...)
fallback_1 = ChatAnthropic(model="claude-3-opus", ...)
fallback_2 = ChatOpenAI(model="gpt-3.5-turbo", ...)  # 저가 fallback

llm = primary.with_fallbacks([fallback_1, fallback_2])
```

- **프롬프트 호환성**: ✅ 문제 없음. `ChatPromptTemplate`은 provider-agnostic. LangChain이 내부적으로 메시지 형식을 변환합니다.
- **Function calling 호환성**: ⚠️ **주의 필요**. `create_tool_calling_agent`는 모델이 tool calling을 지원해야 합니다. GPT-4, Claude 3 모두 지원하므로 OK. 단, fallback 모델이 tool calling 미지원이면 실패합니다. **Gemini는 LangChain `ChatGoogleGenerativeAI`에서 tool calling 지원이 불안정 → fallback 체인에서 제외 권장**.

**2. Fallback 트리거 조건**

**Option B 채택 권장**: 5xx + timeout(30s) + 429

구현 방법: LangChain `with_fallbacks()`는 기본적으로 모든 exception에서 fallback 발동합니다. 특정 에러만 필터하려면:

```python
llm = primary.with_fallbacks(
    [fallback_1, fallback_2],
    exceptions_to_handle=(
        openai.RateLimitError,      # 429
        openai.APITimeoutError,     # timeout
        openai.InternalServerError, # 5xx
        anthropic.InternalServerError,
    ),
)
```

**Option C (QA score 기반)는 후속 개선으로 미룸** — 실시간 QA 평가가 latency를 2배 증가시킴.

**3. 비용 임팩트**

- GPT-4 Turbo: ~$10/1M input, ~$30/1M output
- Claude 3 Opus: ~$15/1M input, ~$75/1M output
- **결론**: Fallback이 빈번하면 비용 증가 가능. `LangFuse`에 fallback 이벤트 로깅하여 모니터링. 사용자에게는 "이 작업은 보조 모델로 처리되었습니다" 표시 정도면 충분.

### 구현 계획

1. `base.py`의 `_create_llm()`에 `fallback_models` 파라미터 추가
2. `settings`에 `FALLBACK_MODELS` 환경 변수 (쉼표 구분)
3. 기존 테스트 100% 호환 유지 (fallback은 optional)
4. fallback 발동 시 LangFuse에 metadata 기록

**예상 변경량**: base.py ~30줄 수정, config.py ~5줄, 테스트 ~40줄

---

## Idea #233: Test Coverage Sprint 🧪

### 판정: ✅ GO — 높은 우선순위 동의, 단 범위 조정 필요

### 현재 테스트 현황

| 항목 | 수치 |
|------|------|
| 총 테스트 수 | 2,177개 |
| 전체 통과 | ✅ 100% |
| app/ 코드 | ~34,700줄 |
| tests/ 코드 | ~45,300줄 |
| 테스트/코드 비율 | 1.3x (테스트가 더 많음) |

**핵심 관찰**: 테스트 *수*는 충분합니다 (2,177개). 문제는 **coverage 분포** — 일부 모듈은 과잉 테스트되고, 핵심 비즈니스 로직은 미커버 가능성.

### 테스트 우선순위 (기획자 제안에 동의 + 보완)

```
1순위: services/ (비즈니스 로직)
  - onboarding_service.py ← 이미 커버됨
  - error_recovery.py ← 방금 81개 추가
  - task_health.py ← 커버됨
  - google_auth.py ← 커버됨
  - 미커버: celery task 실제 실행 경로
  
2순위: agents/ (핵심 Agent 로직)
  - base.py의 run() 메서드 전체 flow
  - research_agent.py의 _scrape_web() 모킹
  - orchestrator.py의 에러 처리 경로

3순위: api/ (통합 테스트)
  - 인증 + 에러 응답 형식 일관성
  - /tasks/{id}/recovery 엔드포인트 (추가 필요)
```

### conftest.py 정비

현재 conftest.py를 확인한 결과, 공통 fixture가 이미 잘 되어 있습니다. 추가 필요:

```python
# conftest.py에 추가 권장
@pytest.fixture
def mock_google_service():
    """Mock Google API service for Sheets/Docs/Slides agents."""
    ...

@pytest.fixture  
def mock_celery_task():
    """Mock Celery task execution for integration tests."""
    ...
```

### 50% 커버리지 목표

- 현재 정확한 커버리지 측정이 필요합니다 (`pytest --cov=app`)
- 45,300줄 테스트 / 34,700줄 코드 비율로 볼 때, 실제 line coverage는 이미 30-40%일 가능성 높음
- **50%까지 올리는 데 8일이 아니라 3-4일이면 충분**할 수 있음
- `pytest-cov` + GitHub Actions CI 설정은 0.5일

---

## Idea #234: Interactive Task Preview 👀

### 판정: ✅ GO (P1) — #232 이후 착수 권장

### 기술 분석

**1. Plan 단계 분리 가능성**

현재 BaseAgent의 `run()` 메서드 (base.py)는 `AgentExecutor.ainvoke()`를 호출하여 plan → execute를 한 번에 수행합니다. 분리 방법:

```python
# 방법 A: 별도 LLM 호출 (권장 — 간단, 기존 코드 수정 최소)
async def preview(self, prompt: str) -> dict:
    """Generate a preview plan without executing."""
    plan_prompt = f"Given this request: '{prompt}'\nList the steps you would take (do NOT execute)."
    response = await self.llm.ainvoke([HumanMessage(content=plan_prompt)])
    return {"steps": response.content, "estimated_time": "..."}

# 방법 B: AgentExecutor의 plan() 사용 (복잡, Agent 내부 의존)
# → 권장하지 않음. LangChain의 plan()은 internal API이며 변경될 수 있음
```

**방법 A 권장** — 기존 Agent 코드 수정 0줄, 새 메서드 1개 추가.

**2. Preview → 실행 연결**

- **처음부터 다시 실행 권장**. Plan 캐싱은 복잡성 대비 이득이 적음 — LLM은 비결정적이므로 동일 plan 보장 불가.
- 단, preview에서 사용자가 수정한 prompt는 저장하여 실행 시 사용.
- Preview는 빠른 모델 (gpt-3.5-turbo)로, 실행은 기본 모델로 → 비용 절감.

### 구현 계획

1. `BaseAgent.preview(prompt)` 메서드 추가 (~20줄)
2. `POST /api/v1/tasks/preview` 엔드포인트 (~30줄)
3. 응답: `{steps: [...], estimated_time: "~2min", estimated_cost: "$0.05"}`
4. 프론트엔드: preview 모달 → "실행" 버튼 → create_task 호출

---

## GO/NO-GO 최종 판정

| Idea | 기획자 | 설계자 | 착수 가능 시점 |
|------|--------|--------|-------------|
| #232 Multi-Model Fallback | ✅ GO (P0) | ✅ **GO** | 즉시 (0.5일) |
| #233 Test Coverage Sprint | ✅ GO (P0) | ✅ **GO** (범위 축소: 3-4일) | #232 이후 |
| #234 Interactive Task Preview | ✅ GO (P1) | ✅ **GO** | #233 이후 (1일) |

### 착수 순서 합의

```
#225 Smart Error Recovery ✅ (완료, 커밋됨)
  → #232 Multi-Model Fallback (0.5일)
  → #233 Test Coverage Sprint (3-4일)
  → #234 Interactive Task Preview (1일)
```

### 기획자 권고 수용

> 아이디어 생성 48시간 중단, 구현/테스트 집중

**동의합니다.** 현재 아이디어만으로도 1-2주치 작업이 있습니다.

---

작성: Dev Codex (2026-02-20 19:30 UTC)
