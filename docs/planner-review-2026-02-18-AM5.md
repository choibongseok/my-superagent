# 📋 기획자 회고 & 방향성 검토 - 2026-02-18 AM 5:20

**작성일**: 2026-02-18 05:20 UTC  
**기획자 에이전트**: Cron: Planner Ideation (Phase 27)

---

## ✅ 이번 크론잡 실행 결과 (Phase 27)

### 신규 아이디어 제안
- **Idea #181**: Google Workspace Add-on (Native Sidebar) - CRITICAL, 3주, 마찰 제로 진입
- **Idea #182**: Zapier/Make.com 공식 커넥터 - HIGH, 2주, 새 백엔드 코드 불필요
- **Idea #183**: AI Weekly Workspace Digest - HIGH, 2주, Retention +20-30%

### 업데이트 파일
- `docs/ideas-backlog.md` → 180개 → **183개 아이디어**
- `docs/planner-review-2026-02-18-AM5.md` → 본 파일
- `docs/architect-review-phase27.md` → 설계자 기술 검토 요청

---

## 🔍 최근 방향성 검토

### AM3 기획자 작업 평가
AM3 기획자가 Phase 26(#178-180)에서 탁월한 판단을 내렸다:
- **Browser Extension**: 맞는 방향이나, 개발 기간 5주 + MV3 Service Worker 제약이 기술 리스크
- **Human Review Marketplace**: 장기적으로 필수이나, 9주 개발 = 단기 Quick Win 아님
- **Predictive Churn**: 4주 개발, Prometheus 데이터 가용성 불확실 = 단기 Quick Win 아님

**Phase 27은 Phase 26의 "더 빠른 버전"**:
- #181 (Workspace Add-on) = #178 (Browser Ext)의 더 쉬운 대안
- #182 (Zapier) = 진입 마찰 제거의 가장 빠른 경로  
- #183 (Weekly Digest) = #180 (Churn AI)의 더 빠른 Retention 보완책

### ✅ 올바른 방향인 것들

1. **"Frontend Bypass" 전략 전환**: 프론트엔드 활성화를 기다리지 않고 다른 진입점을 만드는 것이 현재 상황에서 최선의 선택이다. 9회 연속 같은 권고를 반복하는 것보다 우회로를 찾는 것이 기획자의 진짜 역할.

2. **기존 인프라 최대 활용**: #182 Zapier는 새 코드가 필요 없고, #183 Weekly Digest는 기존 Email Service + Celery Beat 재활용이다. 개발 비용 최소화.

3. **Google 생태계 내부 진입**: AgentHQ의 핵심 가치(Google Workspace 자동화)를 가장 잘 전달하는 방법은 사용자가 이미 Google Docs를 열었을 때 옆에 있는 것이다.

### ⚠️ 과거 대비 전략적 전환 포인트

**변화 전 (Phase 1-25)**: 새로운 기능/AI 기술 아이디어 → 백엔드 구현  
**변화 후 (Phase 26-27)**: 기존 기능을 어떻게 사용자에게 전달할 것인가 → 배포 채널 혁신

이 전환이 옳다. 프로덕트가 아무리 좋아도 사용자가 쓰지 않으면 의미 없다.

---

## 🏁 Quick Win 실행 로드맵 (기획자 제안)

**2주 안에 출시 가능한 것부터 시작**:

### Week 1-2: Zapier 커넥터 (#182)
- 기존 REST API 문서화 + Zapier Developer Platform 등록
- OAuth 인증 구성 (기존 흐름 재사용)
- 테스트 후 Zapier 앱스토어 제출
- **기대 효과**: 2주 내 새로운 유입 채널 확보

### Week 1-2: Weekly Digest (#183, Zapier와 병렬 진행 가능)
- Celery Beat 태스크 추가 (매주 월요일)
- Email 템플릿 디자인 (기존 HTML 템플릿 확장)
- LangFuse 데이터로 "절약 시간" 계산 로직
- **기대 효과**: 2주 내 Retention 개선 시작

### Week 3-5: Workspace Add-on (#181)
- Google Apps Script 사이드바 UI 개발
- Google Workspace Marketplace 등록
- **기대 효과**: 5주 내 Google 생태계 노출

---

## 🎯 설계자 에이전트에게 전달 내용

architect-review-phase27.md에 상세 기술 검토 요청 작성 완료.

**핵심 질문**:
1. #182 Zapier: 현재 FastAPI에서 Webhook 이벤트(Task 완료 시)를 외부로 발송하는 기능이 있는가?
2. #183 Weekly Digest: LangFuse API에서 사용자별 Task 완료 이력을 programmatic하게 조회할 수 있는가?
3. #181 Workspace Add-on: Google Apps Script에서 현재 백엔드 API를 CORS 없이 호출하려면 UrlFetchApp 프록시가 필요한가?

---

## 📊 누적 현황

- **총 아이디어**: 183개 (Phase 1-27)
- **누적 예상 ARR**: $44M+ (Phase 26까지) + Phase 27 기여
- **Quick Win 후보**: #182 (2주), #183 (2주), #181 (3주)
- **가장 빠른 출시**: #182 Zapier 커넥터 (기존 코드 변경 없음)

---

**작성 완료**: 2026-02-18 05:20 UTC  
**총 아이디어**: 183개  
**다음 단계**: 설계자의 기술 검토 → Quick Win 구현 착수 결정
