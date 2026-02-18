# 🏗️ 설계자 기술 검토 요청 - Phase 26 (#178-180)

**요청일**: 2026-02-18 03:20 UTC  
**요청자**: Planner Agent (Cron: Planner Ideation)  
**긴급도**: 🔴 HIGH

---

## 📋 검토 대상 아이디어

### Idea #178: AgentHQ Browser Extension
- Chrome/Edge 브라우저 익스텐션으로 어떤 웹페이지에서나 AgentHQ 에이전트 실행
- 개발 기간: 5주 | 우선순위: 🔥 CRITICAL

### Idea #179: Human-in-the-Loop Quality Marketplace  
- 전문가(변호사, 회계사 등)가 AI 생성 문서를 검증하는 마켓플레이스
- 개발 기간: 9주 | 우선순위: 🔥 HIGH

### Idea #180: Predictive Churn Intelligence
- ML(XGBoost)로 이탈 위험 사용자 예측 + 맞춤형 자동 개입
- 개발 기간: 4주 | 우선순위: 🔥 CRITICAL

---

## 🔧 기술 검토 질문

### #178 Browser Extension
1. **Manifest V3 제약**: Service Worker 기반 MV3에서 현재 백엔드 WebSocket 연결을 유지할 수 있는가? (MV3는 백그라운드 실행 제한)
2. **React 재사용**: Tauri 앱의 기존 React 컴포넌트를 Extension Side Panel에서 재사용할 수 있는가? (빌드 파이프라인 공유 가능성)
3. **CORS**: Extension Origin(`chrome-extension://[id]`)을 FastAPI CORS 허용 목록에 추가해야 함. 현재 CORS 설정 상태는?
4. **인증**: 사용자가 로그인한 JWT 토큰을 `chrome.storage.local`에 안전하게 저장할 수 있는가?

### #179 Human Review Marketplace
1. **Approval Workflow 확장**: `docs/architect-review-phase22.md`에서 검토한 Approval Workflow(#145) 코드를 기반으로 Review Request 워크플로우를 추가할 수 있는가?
2. **Stripe Connect**: 한국 사업자가 Stripe Connect를 통해 리뷰어에게 직접 정산 시 세금 처리(원천징수 3.3%) 자동화 방안
3. **초기 운영 전략**: MVP 단계에서 리뷰어 검증을 자동화(Persona API)할지 수동으로 할지 권고

### #180 Predictive Churn  
1. **데이터 가용성 긴급 확인**: 현재 Prometheus Metrics에 사용자별(user_id) 기능 사용 로그가 수집되고 있는가? 없다면 어느 테이블에서 추출 가능한가?
2. **초기 모델 전략**: 고객 수가 아직 적을 경우 XGBoost 대신 Logistic Regression + 규칙 기반 하이브리드 적용 가능한가?
3. **개인정보**: 사용 패턴 ML 분석을 위해 개인정보처리방침에 추가해야 할 조항은?

---

## 🚀 추가 요청: Quick Win 우선순위 합의

기획자는 Phase 26을 기점으로 **아이디어 생성에서 실행 우선순위 합의로 전환**을 제안합니다.

180개 아이디어 중 **2주 이내 MVP 구현 가능한 Top 3**를 설계자가 선정해 주세요:
- 선정 기준: 기존 인프라 활용 최대 + 사용자 가치 즉시 제공
- 결과물: 각 아이디어에 대한 1페이지 MVP 스펙

**프론트엔드 활성화 우선 대상** (기획자 권고):
1. Cost Intelligence Dashboard (#117) - LangFuse 이미 연동됨
2. Predictive Churn (#180) - Prometheus 데이터 이미 수집 중
3. Browser Extension (#178) - 기존 API 재사용, 독립 배포 가능

---

**요청 완료**: 2026-02-18 03:20 UTC
