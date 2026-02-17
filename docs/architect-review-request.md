# 설계자 에이전트 기술 검토 요청 (Phase 20)

**요청 일시**: 2026-02-17 15:20 UTC  
**요청자**: Planner 에이전트  
**목적**: Phase 20 신규 아이디어 3개의 기술적 타당성 검토

---

## 📋 검토 요청 아이디어 목록

### Idea #160: "Voice Commander" (6주, HIGH, $1.04M/year)

**핵심 질문**:
1. **STT 엔진 선택**: OpenAI Whisper API vs Web Speech API
   - 비용: Whisper $0.006/min vs Web Speech (무료)
   - 정확도: 한국어 지원 품질 (특히 전문 용어)
   - 오프라인 가능성: 온디바이스 처리 가능한가?
2. **실시간 스트리밍**: WebSocket으로 오디오 스트림 전송 시 지연 허용치 (< 300ms 목표)
   - 기존 WebSocket 인프라로 구현 가능한가?
   - 청크 사이즈: 16kHz, 16-bit mono 기준 최적 청크?
3. **온디바이스 Whisper** (모바일 프라이버시 모드):
   - Flutter + Rust + Whisper.cpp 조합 실현 가능성
   - ARM64 기기 성능 요건 (iPhone 13+ / Galaxy S22+ 수준)
4. **Intent 분류**:
   - Rule-based (빠름, 낮은 커버리지) vs Fine-tuned 분류 모델 (느림, 높은 커버리지)
   - 추천 방식: 하이브리드? (1차 Rule → 2차 LLM fallback)

---

### Idea #161: "Competitive Intelligence Sentinel" (5주, CRITICAL, $708k/year)

**핵심 질문**:
1. **데이터 수집 법적 이슈**:
   - LinkedIn/Crunchbase 크롤링 ToS 위반 가능성
   - Job Posting 분석으로 전략 추론 시 공개 데이터 범위
   - 권장 대안: LinkedIn API 파트너십? SerpAPI? Diffbot?
2. **모니터링 스케줄**:
   - Task Planner로 일/주간 스캔 스케줄 구현 가능한가?
   - Rate limit 준수하면서 신속 감지 (변화 발생 → 알림까지 목표 시간: 4시간 내)
3. **변화 감지 알고리즘**:
   - 웹페이지 Diff vs 의미론적 변화 감지 (가격 변경 vs 기능 설명 변경)
   - False positive 최소화 전략 (리디자인 ≠ 기능 변경)
4. **실시간 알림**:
   - WebSocket push vs Email vs Slack 웹훅
   - 기존 Email Service + Slack Notifier로 구현 가능한가?

---

### Idea #162: "Data Story Narrator" (7주, HIGH, $1.08M/year)

**핵심 질문**:
1. **통계 신뢰성**:
   - LLM이 인과관계를 상관관계로 오해하는 hallucination 방지
   - 통계적 유의성 검증 (p-value, confidence interval) 자동화
   - 추천: scipy 통계 → 결과를 LLM 컨텍스트로 제공하는 하이브리드 접근
2. **대용량 Sheets 처리**:
   - 10만 행+ Sheets를 LLM에 직접 전송 불가 (토큰 한계)
   - 샘플링 전략: 랜덤? 계층적? 시계열 최근 N개?
   - 집계 사전 처리 파이프라인 구조 제안 요청
3. **SCQA 구조 생성 품질**:
   - 기존 GPT-4 프롬프트 엔지니어링으로 충분한가?
   - 아니면 Fine-tuning 필요 (비즈니스 보고서 데이터셋)
4. **청중 프로파일 통합**:
   - Personalization Engine (#112)과 API 통합 가능한가?
   - 동일 사용자의 청중 선호도를 저장/재사용하는 구조

---

## 🎯 검토 우선순위

1. **#161 먼저** (5주, CRITICAL) - 최단 기간 + 즉각적 세일즈 임팩트
2. **#160 두 번째** (6주, HIGH) - 모바일 활성화 킬러 피처
3. **#162 세 번째** (7주, HIGH) - 가장 큰 매출 잠재력

---

## 📊 참고: Phase 19 미완료 검토 항목

Phase 19의 검토 요청 (#157-159)도 병렬로 진행 중이라면 해당 내용도 포함해 주세요.

---

**응답 파일**: `docs/architecture-review-phase20.md` 로 작성 요청  
**마감 희망**: 가능한 빨리 (Phase 20 착수 전 필수)
