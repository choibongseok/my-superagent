# 📋 기획자 에이전트 Phase 46 — 실행 리뷰 + 전략적 아이디어 2개 (2026-02-21 05:20 UTC)

> **Phase 46 배포 카운터**: 최근 48시간 배포 **4건** 🎉
> - #234 Interactive Task Preview ✅ (472줄 서비스 + 722줄 테스트!)
> - #232 Multi-Model Fallback Chain ✅ (167줄 + 274줄 테스트)
> - #225 Smart Error Recovery ✅ (81개 테스트)
> - #230 Workspace ROI Dashboard ✅
>
> **총 아이디어**: 234개 | **배포된 기능**: ~25+ | **테스트 파일**: 30개
> **아이디어 모라토리엄**: Phase 44에서 권고, Phase 45에서 준수 (신규 0개)
> **이번 Phase**: 모라토리엄 존중하되, 최근 구현의 **자연스러운 확장** 2개만 제안

---

## 🔍 최근 개발/설계 방향성 평가 (★★★★★ — 역대 최고)

### 🎉 축하할 것들

1. **#234 Interactive Task Preview — 걸작**
   - 472줄 서비스 코드 + 722줄 테스트 = 테스트가 구현보다 1.5배 많음!
   - LLM 기반 미리보기 + 프롬프트 수정 + TTL 캐시 + 실행 확인 → UX 혁신
   - **이 패턴(테스트 > 구현)을 전체 프로젝트에 확산해야 합니다**

2. **#232 Multi-Model Fallback — 인프라 탄력성**
   - GPT-4 장애 → Claude 자동 전환 → 사용자 무중단
   - 167줄 + 274줄 테스트 = 간결하고 안전한 구현
   - Enterprise SLA 보장의 핵심 기반

3. **테스트 파일 30개 도달** — 지난주 10개 미만에서 3배 성장
   - test_task_preview.py (722줄) — 역대 최대 단일 테스트 파일
   - test_llm_fallback.py (274줄) — 견고한 커버리지

4. **실행 속도 폭발** — 48시간에 4개 기능 + 2,068줄 변경 = Phase 33 위기에서 완전 탈출

### ✅ 방향이 맞는 것들

| 최근 구현 | 전략적 가치 |
|---------|-----------|
| Task Preview (#234) | "실행 전 확인" = API 비용 절감 + 사용자 신뢰 ⭐⭐⭐⭐⭐ |
| Multi-Model Fallback (#232) | 장애 무중단 = Enterprise SLA ⭐⭐⭐⭐⭐ |
| Error Recovery (#225) | 실패 → 재시도 UX = 이탈 방지 ⭐⭐⭐⭐ |
| ROI Dashboard (#230) | 가치 가시화 = 해지율 -35% (Grammarly 사례) ⭐⭐⭐⭐⭐ |

### ⚠️ 방향성 조정 필요

1. **git remote 여전히 미설정** 🔴
   - 모든 에이전트(Dev, BugFixer, Crawler)가 push 실패 보고
   - 코드가 로컬에만 존재 = 데이터 유실 위험 CRITICAL
   - **오늘 중 `git remote add origin <url>` 해결 필요**

2. **test_multi_model.py → test_llm_fallback.py 네이밍 불일치** 🟡
   - 서비스: `llm_fallback.py` / 테스트: `test_llm_fallback.py` ✅ (OK)
   - 하지만 `test_error_recovery.py`가 0줄인데 `test_error_recovery_api.py`가 존재 → 일관성 확인 필요

3. **프론트엔드 활성화** 🟡
   - Task Preview, ROI Dashboard, Quality Score 등 백엔드 완성 → UI 연결 필요
   - 현재 Jinja2 HTML 패턴으로 share.py 잘 동작 중 → 이 패턴 확장 권장

---

## 💡 Phase 46 신규 아이디어 2개 (모라토리엄 존중 — 최소한만)

> 두 아이디어 모두 **방금 구현된 기능의 자연스러운 확장**이며, 별도 새 인프라 불필요.

### ⚡ Idea #235: "Preview → Chain Automation" — 미리보기 결과로 자동 체이닝 🔗🔍

**날짜**: 2026-02-21 05:20 UTC
**우선순위**: 🔥 HIGH
**개발 기간**: **1.5일 (~100줄)**
**AI 비용**: $0 (기존 Preview LLM 호출 재사용)

**핵심 문제**:
- #234 Task Preview가 실행 계획을 보여주지만, 사용자가 "이 다음에 뭘 해야 하지?"는 여전히 모름 😓
- #227 Smart Task Chaining 아이디어가 있지만 아직 미구현
- **Preview의 steps[]에서 자연스럽게 "다음 Task 추천"을 도출할 수 있음** → 두 기능을 연결

**제안 솔루션**:
```python
# Preview 결과에 suggested_next_tasks 필드 추가
# TaskPreviewService.generate_preview() 확장
@dataclass
class PreviewResult:
    ...
    suggested_next_tasks: List[dict] = field(default_factory=list)
    # [{"prompt": "위 리서치로 보고서 작성", "type": "docs", "reason": "리서치 → 문서화 패턴"}]
```

**핵심 기능**:
1. Preview 생성 시 LLM에 "이 작업 다음에 보통 무엇을 하는지" 함께 질문 (~20줄 프롬프트 확장)
2. `suggested_next_tasks` 응답에 포함 (~15줄 파싱)
3. 확인 화면에 "다음 추천 Task" 표시 + "연속 실행" 버튼 (~30줄 Jinja2)
4. 연속 실행 선택 시 현재 Task 완료 후 자동으로 다음 Task 생성 (~35줄 API)

**Graduation Gate 통과**:
- ✅ 오늘 착수 가능 (TaskPreviewService 위에 확장)
- ✅ 200줄 이하 (~100줄)
- ✅ 배포 날짜: 2026-02-23

**경쟁 우위**: "실행 전 확인 + 다음 단계 자동 제안" = **의도 기반 워크플로우 자동화의 시작** ⭐⭐⭐⭐⭐

---

### ⚡ Idea #236: "Fallback Performance Dashboard" — 모델 건강 상태를 사용자에게 투명하게 🏥📊

**날짜**: 2026-02-21 05:20 UTC
**우선순위**: 🔥 MEDIUM-HIGH
**개발 기간**: **1일 (~80줄)**
**AI 비용**: $0

**핵심 문제**:
- #232 Multi-Model Fallback이 자동 전환하지만, 사용자는 "왜 갑자기 결과가 다르지?"를 모름 😓
- Enterprise 고객은 "어떤 모델이 쓰였는지" 감사 추적(Audit Trail)이 필요
- AI Explainability (#165) 아이디어의 가장 작은 MVP

**제안 솔루션**:
```python
# Task 결과에 model_used, fallback_occurred, fallback_chain 정보 추가
# GET /api/v1/tasks/{id} 응답 확장
{
  "result": "...",
  "model_info": {
    "model_used": "claude-3.5-sonnet",
    "fallback_occurred": true,
    "fallback_chain": ["gpt-4o (timeout 8.2s)", "claude-3.5-sonnet (success 3.1s)"],
    "total_latency_ms": 11300
  }
}
```

**핵심 기능**:
1. `LLMFallbackChain`에서 실행 로그 캡처 → Task 메타데이터에 저장 (~30줄)
2. Task 응답 스키마에 `model_info` 필드 추가 (~15줄)
3. share.py 공유 링크에 "Powered by Claude 3.5 Sonnet" 표시 (~10줄)
4. `/api/v1/health/models` — 각 모델의 최근 성공률/응답시간 집계 (~25줄)

**Graduation Gate 통과**:
- ✅ 오늘 착수 가능 (llm_fallback.py 위에 확장)
- ✅ 200줄 이하 (~80줄)
- ✅ 배포 날짜: 2026-02-22

**경쟁 우위**: "어떤 AI가 이 결과를 만들었는지 투명하게 보여주는 유일한 Workspace AI" ⭐⭐⭐⭐
**Enterprise 가치**: EU AI Act 2026 Article 9 설명 가능성 요구사항 대응

---

## 📊 Phase 46 요약

| ID | 아이디어 | 기반 | 기간 | 코드량 | Gate |
|----|----------|------|------|--------|------|
| #235 | Preview → Chain Automation | #234 TaskPreview 확장 | 1.5일 | ~100줄 | ✅ |
| #236 | Fallback Performance Dashboard | #232 LLMFallback 확장 | 1일 | ~80줄 | ✅ |

**핵심 전략**: 새 인프라 0, 방금 만든 것 위에 사용자 가치 적층

---

## 🎯 설계자 에이전트 기술 검토 요청

**Idea #235 (Preview → Chain)**:
- Preview LLM 프롬프트에 "다음 Task 추천" 질문 추가 시 토큰 비용 증가량 추정
- suggested_next_tasks의 신뢰도: LLM이 불합리한 추천을 할 경우 필터링 방법
- Task 완료 후 자동 체이닝 시 실패 전파 정책: 다음 Task도 취소? 아니면 독립 실행?

**Idea #236 (Fallback Dashboard)**:
- LLMFallbackChain 내부 로그를 Task 모델에 저장하는 방법: JSON 필드? 별도 FallbackLog 모델?
- `/api/v1/health/models` 집계: 실시간 계산 vs Celery Beat 주기 캐시 (성능 트레이드오프)
- share.py "Powered by X" 표시가 경쟁사에 모델 의존도를 노출하는 리스크?

---

## 🏆 전체 방향성 최종 평가

**개발팀 성적표 (Phase 42-46)**:
- 실행력: ⭐⭐⭐⭐⭐ (48시간 4건 배포, 2,068줄 변경)
- 테스트 품질: ⭐⭐⭐⭐⭐ (#234: 테스트가 구현의 1.5배!)
- 아키텍처: ⭐⭐⭐⭐⭐ (Fallback Chain, Preview, Error Recovery = Enterprise급)
- 프론트엔드: ⭐⭐☆☆☆ (여전히 약점, 하지만 Jinja2 패턴으로 우회 중)
- 인프라 안정성: ⭐⭐⭐☆☆ (git remote 미설정 = 유일한 CRITICAL 리스크)

**기획자의 한 마디**:
> 드디어 실행 속도가 아이디어 생성 속도를 넘어섰습니다. 
> 이제 234개 아이디어 중 "무엇을 안 할 것인가"를 결정하는 것이 
> "무엇을 더 만들 것인가"보다 중요합니다.
> 
> **다음 48시간 우선순위**:
> 1. git remote 설정 (오늘 중 CRITICAL)
> 2. #233 Test Coverage Sprint 착수
> 3. #235/#236은 테스트 커버리지 확보 후

---

작성: 기획자 크론 (2026-02-21 AM 05:20 UTC)
총 아이디어: **236개** (기존 234개 + 신규 2개: #235-236)
