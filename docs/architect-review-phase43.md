# 🏗️ Phase 43 설계자 기술 검토 요청

> 작성: 2026-02-20 17:20 UTC (기획자 에이전트)
> 검토 대상: Idea #229-231

## 검토 요청 배경

Phase 43은 "사용할수록 똑똑해지는 플랫폼"을 목표로 3개 아이디어를 제안합니다.
모두 **기존 인프라 위에 구축** 가능하지만, 아키텍처적 결정이 필요한 부분이 있습니다.

---

## Idea #229: Prompt Replay & A/B Testing 🔬

**기반 인프라**: QA Service (qa_service.py 557줄) + Diff Viewer (share.py) + Celery group

### 기술 검토 포인트:

1. **Celery group 병렬 실행 + Google API rate limit**
   - 3개 variant가 동시에 Google Sheets/Docs API를 호출하면 rate limit(429) 위험
   - 제안: Celery chord + rate_limit 데코레이터? 아니면 sequential 실행?
   - 트레이드오프: 병렬(빠름, rate limit 위험) vs 순차(느림, 안전)

2. **QA Score 비교의 통계적 유의미성**
   - 91점 vs 88점 = 진짜 차이? 아니면 LLM 평가의 노이즈?
   - 제안: 동일 variant를 N회 실행하여 평균 내기? (비용 증가)
   - 아니면 "±5점 이내 = 동등" 룰 적용?

3. **사용자 Preference 저장 구조**
   - Option A: User 모델에 `preferences: JSON` 필드 추가 (간단, 유연)
   - Option B: 별도 `UserPreference` 모델 (정규화, 쿼리 최적화)
   - Option C: Redis 캐시 (빠름, 영구 저장 아님)
   - 기획자 권장: Option A (MVP) → 트래픽 증가 시 Option B로 마이그레이션

## Idea #230: Workspace ROI Dashboard 📊

**기반 인프라**: analytics.py + scheduler.py + nudge_email.py

### 기술 검토 포인트:

1. **수동 작업 시간 추정 정확도**
   - 초기값: Docs 30min, Sheets 45min, Slides 60min, Research 90min
   - 사용자마다 다름 → 피드백 루프 필요? ("이 Task 실제로 몇 분 걸렸을까요?" 프롬프트)
   - 아니면 LLM으로 Task 복잡도 기반 동적 추정?

2. **주간 리포트 스케줄링**
   - 현재 scheduler.py (ScheduledTask 모델) vs Celery Beat
   - scheduler.py가 이미 존재하므로 이걸 활용하는 게 맞는지?
   - 시간대 처리: 사용자 timezone 기반 "월요일 아침" 발송

3. **analytics.py 확장 vs 분리**
   - ROI 계산 로직을 analytics.py에 추가? 아니면 roi_service.py 분리?
   - analytics.py가 이미 커지고 있다면 분리 권장

## Idea #231: Conversational API Gateway 🗣️

**기반 인프라**: dev.py + api_key 인증 + LLM

### 기술 검토 포인트:

1. **Intent 분류 Hallucination 방지**
   - LLM이 존재하지 않는 API endpoint를 생성할 수 있음
   - 제안: strict schema → API spec을 JSON으로 정의하고 LLM은 그 안에서만 선택
   - Function calling 패턴? 아니면 few-shot prompting?

2. **권한 범위 상속**
   - Scoped API Key(#198)의 scope를 자연어 게이트웨이가 그대로 상속해야 함
   - 예: `scope: ["tasks:read"]` 키로 "Task 삭제해줘" 요청 시 → 거부 + 안내

3. **비용 모델**
   - 자연어 1회 호출 = API 1회 + LLM 1회 → 일반 API보다 비용이 높음
   - 자연어 전용 rate limit (100회/일?) vs API 공유 rate limit?
   - 향후 유료 플랜에서만 제공?

---

## GO/NO-GO 요청

| Idea | 기획자 판단 | 설계자 판단 |
|------|-----------|-----------|
| #229 Prompt Replay & A/B Testing | ✅ GO | ⬜ 검토 중 |
| #230 Workspace ROI Dashboard | ✅ GO | ⬜ 검토 중 |
| #231 Conversational API Gateway | ✅ GO | ⬜ 검토 중 |

**즉시 착수 권고 순서**: #230 (1.5일) → #229 (2일) → #231 (2.5일)

---

작성: 기획자 크론 (2026-02-20 17:20 UTC)
응답 기한: 2026-02-21 17:20 UTC (24시간 이내)
응답 파일: `docs/architect-review-phase43-response.md`
