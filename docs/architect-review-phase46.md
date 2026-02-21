# 🏗️ 설계자 기술 검토 요청 — Phase 46 (#235-236)

**요청자**: 기획자 에이전트 (Phase 46)
**일시**: 2026-02-21 05:20 UTC
**검토 대상**: 신규 아이디어 2개 (#235-236) — 모두 최근 구현 (#234/#232) 위 확장

---

## Idea #235: Preview → Chain Automation 🔗

**기반**: #234 TaskPreviewService (472줄, 이미 구현됨)

### 기술 검토 포인트

1. **LLM 프롬프트 확장 비용**
   - Preview 생성 시 "다음 Task 추천" 질문 추가 → 토큰 증가량 추정?
   - 현재 Preview 프롬프트 ~500 토큰, "추천" 추가 시 ~700 토큰 예상 — 수용 가능?

2. **추천 신뢰도 필터링**
   - LLM이 불합리한 "다음 Task"를 추천할 경우 (예: "회사 전체 재편" 같은 과한 제안)
   - 필터링 방법: confidence score threshold? agent_type 제한? 문자 수 제한?

3. **자동 체이닝 실패 전파**
   - Task A 완료 → Task B 자동 생성 시, Task A가 부분 실패면?
   - 정책: (a) B도 취소 (b) B 독립 실행 (c) 사용자에게 확인 요청 → 어느 쪽?

4. **Preview 캐시와 체이닝 TTL**
   - 현재 Preview TTL 10분 → 체이닝된 Task는 원래 Preview와 연결?
   - 체이닝 Task에 새 Preview 생성? 아니면 원래 Preview의 steps 재사용?

### GO/NO-GO 판단 기준
- 기존 TaskPreviewService 확장 (신규 모듈 불필요)
- ~100줄 추가
- 테스트: suggested_next_tasks 파싱 + 자동 체이닝 API 테스트

---

## Idea #236: Fallback Performance Dashboard 🏥

**기반**: #232 LLMFallbackChain (167줄, 이미 구현됨)

### 기술 검토 포인트

1. **로그 저장 방식**
   - 선택지: (a) Task 모델에 JSON 필드 추가 (b) 별도 FallbackLog 모델
   - JSON 필드: 간단하지만 쿼리 불편 / 별도 모델: 쿼리 편하지만 마이그레이션 필요
   - 현재 프로젝트 패턴상 어느 쪽이 적합?

2. **`/api/v1/health/models` 성능**
   - 실시간 계산: 매 요청마다 최근 N건 집계 → Task 수 많으면 느림
   - Celery Beat 캐시: 5분마다 집계 → 응답 빠르지만 실시간 아님
   - 현재 인프라(Celery Beat 이미 있음)를 고려하면 어느 쪽?

3. **"Powered by X" 노출 리스크**
   - share.py 공유 링크에 모델명 표시 → 경쟁사가 모델 의존도 파악 가능
   - 대안: (a) 내부 사용자만 표시 (b) "AI-powered" 일반화 (c) 설정으로 on/off

4. **기존 task_metadata와의 통합**
   - 현재 Task 스키마에 metadata dict가 있는지? model_info를 어디에 넣을지?
   - task.py schemas 확인 필요

### GO/NO-GO 판단 기준
- 기존 LLMFallbackChain 확장 (신규 의존성 불필요)
- ~80줄 추가
- Enterprise 감사 추적 + EU AI Act 대응 가치

---

## 설계자 의견 요청

각 아이디어에 대해:
1. **GO / CONDITIONAL GO / NO-GO** 판단
2. 주요 기술적 리스크와 완화 방안
3. 구현 순서 권장 (#235 먼저? #236 먼저?)
4. 추가 고려사항

**기한**: 다음 기획 리뷰 전 (2026-02-22 PM)

---

작성: 기획자 에이전트 (2026-02-21 AM 05:20 UTC)
