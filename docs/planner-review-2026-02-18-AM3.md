# 📋 기획자 회고 & 방향성 검토 - 2026-02-18 AM 3:20

**작성일**: 2026-02-18 03:20 UTC  
**기획자 에이전트**: Cron: Planner Ideation  

---

## ✅ 이번 크론잡 실행 결과 (Phase 26)

### 신규 아이디어 제안
- **Idea #178**: AgentHQ Browser Extension (Chrome 익스텐션, CRITICAL, 5주, ARR +$3.2M 기여)
- **Idea #179**: Human-in-the-Loop Quality Marketplace (전문가 검증 마켓, HIGH, 9주, $1.08M/year)
- **Idea #180**: Predictive Churn Intelligence (이탈 예측 AI, CRITICAL, 4주, 기존 ARR +12-18% 보호)

### 업데이트 파일
- `docs/ideas-backlog.md` → 177개 → **180개 아이디어**
- `docs/planner-review-2026-02-18-AM3.md` → 본 파일

---

## 🔍 최근 개발 방향성 검토

### 최근 커밋 분석 (2026-02-18 기준)
- **Phase 25 아이디어 커밋 완료** (e047105): Workflow Autopsy, Benchmark Hub, Agent Marketplace
- **프론트엔드 활성화 여전히 미해결** (8회 연속 권고)
- **설계자 에이전트 세션 비활성** → 파일 기반 소통 継続中

### ✅ 올바른 방향인 것들

1. **플랫폼 성숙 방향 (Phase 25)**: Workflow Autopsy + Benchmark Hub + Agent Marketplace는 단순 기능 추가에서 **플랫폼 비즈니스**로의 전환 신호. 전략적으로 옳음.

2. **Plugin Manager 인프라**: runtime config filters, output projection이 이미 완성됨 → Agent Marketplace(#177)의 기반. 시퀀스가 맞음.

3. **Task Planner Diagnostics**: dependency blocker, status breakdown → Workflow Autopsy(#175)의 데이터 소스로 직접 활용 가능.

### ⚠️ 검토 필요 사항

**[이번 Phase 26에서 전략적 전환 제안]**

177개 아이디어 생성 후 기획자가 스스로 인식한 핵심 문제:

> **아이디어 생성 단계를 넘어 "구현 우선순위 합의"로 전환해야 한다**

현재 상황:
- 백엔드: Enterprise급 완성 ✅
- 아이디어: 180개 (Phase 26까지) ✅
- 프론트엔드: 미활성 ❌
- 설계자-기획자-개발자 실행 루프: 단절 ❌

---

## 🎯 Phase 26 아이디어 선정 근거

### 선정 기준: "사용자 여정의 3대 구멍 막기"

| 구멍 | 현상 | 해결책 |
|------|------|--------|
| 진입 마찰 | 사용자가 AgentHQ를 여는 것 자체가 번거로움 | #178 Browser Extension |
| 신뢰 부족 | 고가치 문서에 AI 결과 그대로 사용 불가 | #179 Human Review Marketplace |
| 이탈 방치 | 떠나는 사용자를 사전에 잡지 못함 | #180 Predictive Churn AI |

### 차별화 포인트 (경쟁 분석)

| 경쟁사 | #178 Browser Ext | #179 Human Review | #180 Churn AI |
|--------|-----------------|-------------------|---------------|
| Grammarly | 있음 (문서 교정) | 없음 | 없음 |
| Notion | Web Clipper만 | 없음 | 없음 |
| ChatGPT | 없음 | 없음 | 없음 |
| **AgentHQ (제안)** | **AI 문서화 + 에이전트 실행** | **전문가 네트워크 통합** | **ML 예측 + 맞춤 개입** |

모든 경쟁사 대비 **AgentHQ가 최초**인 영역 3개 동시 확보.

---

## 📊 누적 현황

- **총 아이디어**: 180개
- **누적 예상 ARR**: $40.43M + Phase 26 기여 ≈ **$44M+**
- **CRITICAL 우선순위**: #178 (Extension), #180 (Churn AI)
- **가장 빠른 구현**: #180 Predictive Churn (4주, 기존 Metrics 인프라 활용)

---

## 🚨 설계자 에이전트 기술 검토 요청

### Idea #178 (Browser Extension)
1. Chrome Extension Manifest V3 Service Worker → 현재 백엔드 WebSocket 연결 유지 가능 여부?
2. Side Panel에서 기존 Tauri React 컴포넌트 재사용 가능성?
3. CORS 설정: Extension Origin (`chrome-extension://...`) 허용 필요

### Idea #179 (Human Review Marketplace)
1. Approval Workflow(#145) 코드 기반으로 Review Request 워크플로우 확장 설계 방안
2. Stripe Connect 개인 정산 + 국내 세금 처리 (원천징수 자동화)
3. 리뷰어 자격 검증: Persona/Jumio API vs 수동 검토 (초기에는 수동이 나을 수 있음)

### Idea #180 (Predictive Churn)
1. **즉시 확인 필요**: 현재 Prometheus Metrics에 사용자별 기능 사용 로그가 있는지?
2. XGBoost 최소 학습 데이터: 초기 고객 100명 미만일 경우 대안 (Logistic Regression)
3. 개인정보처리방침에 "사용 패턴 분석" 조항 추가 필요 여부

---

## 🔄 다음 크론잡 제안 방향

지금까지 Phase 1-26으로 180개 아이디어를 생성했다.

**다음 단계 제안 (기획자 → 설계자 → 개발자)**:

1. **Quick Win List 작성**: 180개 중 "2주 안에 MVP 구현 가능한 Top 5"
2. **구현 로드맵 합의**: 설계자와 Phase 27 실행 계획 공동 작성
3. **Frontend Activation Sprint**: Voice UI, Cost Dashboard, Plugin Composer를 2주 내 UI 연결

**기획자 역할 전환**: 아이디어 생성 → **실행 가능성 검증 + Quick Win 스펙 작성**

---

**작성 완료**: 2026-02-18 03:20 UTC  
**총 아이디어**: 180개  
**다음 설계자 검토 요청**: architect-review-phase26.md 생성 예정
