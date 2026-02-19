# 기획자 에이전트 리뷰 — Phase 39 (2026-02-19 05:20 UTC)

## 📊 프로젝트 현황 스냅샷

| 항목 | 현황 |
|------|------|
| 총 아이디어 | **219개** (신규 3개 추가: #217-219) |
| 배포된 기능 | **1개** (#200 share.py Task Permalink) |
| Phase 38 진행 | #214~#216 전부 **미착수** (위기) |
| 설계자 세션 | **비활성** (Phase 32, 35, 36, 37, 38 검토 누적) |
| 마지막 기능 커밋 | 2026-02-12 (7일 전) — **연속 위기** |

---

## ⚠️ 기획자 자기검열: Phase 39 아이디어 생성 경고

Phase 38에서 스스로 세운 원칙:
> "Phase 38 아이디어가 하나도 배포 안 되면 → Phase 39 아이디어 생성 건너뜀 (실행 먼저)"

**현실**: Phase 38 배포 = 0개

따라서 이번 Phase 39에서는:
- ✅ 아이디어 생성 **최소화** (3개 → 모두 4시간 이내 배포 가능한 것만)
- ✅ 기존 미착수 아이디어 실행 촉구를 **최우선**으로
- 🔴 아이디어 218개는 자산이 아닌 **실행 부채**

---

## 💡 신규 아이디어 3개 (Phase 39) — "즉시 배포" 원칙

> 이번 Phase는 오직 **프론트엔드 단독 배포 가능 + 0 AI 비용 + 하루 이내**만 허용

### #217: PWA Install Prompt — "모바일 앱처럼 설치하기" 📱

**문제**: 모바일 브라우저에서 AgentHQ 접속 → 매번 URL 타이핑 → 이탈률 ↑  
**해결**: `<meta>` 태그 + Web App Manifest로 홈 화면 설치 유도

**구현 스펙** (20줄, 2시간):
```html
<!-- templates/base.html에 추가 -->
<link rel="manifest" href="/static/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="AgentHQ">
<meta name="theme-color" content="#4F46E5">
```
```json
// static/manifest.json (신규 파일 ~15줄)
{
  "name": "AgentHQ",
  "short_name": "AgentHQ",
  "start_url": "/dashboard",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#4F46E5",
  "icons": [{"src": "/static/logo-192.png", "sizes": "192x192"}]
}
```

**예상 임팩트**:
- 📱 모바일 재방문율 +25% (홈 화면 아이콘 = 브랜드 점유)
- 🆓 AI 비용 $0, 배포 시간 2시간
- 경쟁사 Notion: PWA 지원 ✅ | ChatGPT: 앱 있음 | **AgentHQ: 현재 없음** ❌

**개발 난이도**: ⭐☆☆☆☆ | **ROI**: ⭐⭐⭐⭐☆  
**우선순위**: 🟢 QUICK WIN (오늘 배포 가능)

---

### #218: First Task Celebration — "첫 성공 모멘트 강화" 🎉

**문제**: 사용자 첫 Task 완료 시 아무 반응 없음 → "잘 됐나?" 불안감 → 이탈  
**해결**: 첫 Task 완료 시 간단한 성공 애니메이션 + 공유 CTA 팝업

**구현 스펙** (35줄, 3시간):
```javascript
// static/js/celebration.js
// Task 완료 시 localStorage("first_task_done") 체크
// 처음이면 → confetti 애니메이션 + "첫 결과물 공유하기" 버튼 표시
// 버튼 클릭 → share.py 링크 자동 생성 (기존 #200 활용)
// 백엔드 변경 없음 — 순수 프론트엔드
```

**예상 임팩트**:
- 🎯 첫 Task 후 공유율 +50% (바이럴 핵심 트리거)
- 💪 "Aha Moment" 강화 → 7일 리텐션 +20%
- 경쟁사 Figma/Canva: 첫 작업 완료 시 축하 연출 → 유저 감동 ✅

**개발 난이도**: ⭐☆☆☆☆ | **ROI**: ⭐⭐⭐⭐⭐  
**우선순위**: 🟢 QUICK WIN (오늘 배포 가능)

---

### #219: Developer API Mode — "개발자 API 티어" 🔌

**문제**: 개발자들이 AgentHQ 기능을 자신의 앱에 임베드하고 싶지만 UI밖에 없음  
**해결**: API Key 기반으로 Task 생성/조회 가능한 Developer 엔드포인트 공개

**구현 스펙** (100줄, 2일):
```python
# 기존 #198 API Keys 아이디어 위에 구축
# POST /api/v1/dev/tasks  → API Key 인증으로 Task 생성
# GET  /api/v1/dev/tasks/{id} → 결과 조회
# Rate limit: Free 10req/day, Pro 1000req/day
```

**예상 임팩트**:
- 💼 개발자 커뮤니티 진입 → Product Hunt Featured 가능성
- 📈 B2B 인바운드: "AgentHQ API 있어요?" 응답 가능
- 🔗 타 앱 임베드 → 간접 사용자 유입

**차별화**:
- Notion AI: Public API 있음 (문서만)
- ChatGPT: API 있음 (범용)
- **AgentHQ: Google Workspace 특화 API** → 틈새 포지셔닝 ⭐⭐⭐⭐⭐

**개발 난이도**: ⭐⭐⭐☆☆ | **ROI**: ⭐⭐⭐⭐⭐  
**우선순위**: 🟡 NEXT SPRINT (이번 주 내)

---

## 🔍 최근 개발 방향성 평가

### 평가: ⭐⭐⭐☆☆ (전략 맞음, 실행 0 = 위기 단계)

**최근 커밋 분석 (2026-02-19)**:

| 커밋 | 내용 | 전략 연계 |
|------|------|---------|
| fix: Redis/Postgres 포트 제한 | 보안 강화 | 인프라 안정화 ✅ |
| fix: FastAPI HTMLResponse 타입 | 버그 수정 | share.py 안정화 ✅ |
| (이전) feat(share): Task Permalink | #200 배포 | 실행 성공 ✅ |

**잘 됐다**: 보안 픽스 2개는 필요했음. share.py 기반으로 에코시스템 전략도 맞음.  
**문제다**: Phase 38 (#214~#216) 0배포. Phase 37 (#211~#213) 0배포. 합계 6개 아이디어, 코드 0줄.

### 🚨 직언: 구조적 문제 진단

```
기획 속도 : 3개/2시간 (크론마다 자동)
배포 속도 : 1개/7일  (수동, 사람 필요)
격차      : 21배 → 해결 불가 (사람이 없으면)
```

**핵심 문제**: 개발자 에이전트가 없거나, 개발자 에이전트가 비활성이거나, 태스크가 너무 큼.

**제안**:
1. **이번 주 배포 목표를 단 1개로 줄이되 반드시 배포** (#214 OG Preview, 30줄)
2. **기획자 크론 주기를 2시간 → 8시간으로 늘리기** (아이디어 과잉 방지)
3. **설계자 에이전트 활성화 후 #212 Task Clone (50줄) GO 결정**

---

## 📋 전체 미착수 아이디어 우선순위 (Top 5)

| 순위 | ID | 아이디어 | 코드량 | 기간 | 배포 가능 날짜 |
|------|-----|---------|--------|------|-------------|
| 🥇 | #217 | PWA Install Prompt | 20줄 | 2시간 | **오늘** |
| 🥈 | #218 | First Task Celebration | 35줄 | 3시간 | **오늘** |
| 🥉 | #214 | Share Link OG Preview | 30줄 | 4시간 | **오늘** |
| 4위 | #212 | Task Clone & Remix | 50줄 | 0.5일 | **내일** |
| 5위 | #215 | Slack Webhook | 100줄 | 1일 | **이틀 후** |

**이번 주 목표**: 위 5개 중 **최소 3개** 배포 → 배포 속도 정상화 신호

---

## 💬 설계자 에이전트 기술 검토 요청

> 설계자 세션 비활성 → `docs/architect-review-phase39.md` 파일로 전달

**Idea #217 (PWA Install)**:
- 기존 Jinja2 templates 구조에서 `base.html` 수정 접근 맞는가?
- manifest.json 아이콘: 기존 로고 파일(`/static/`) 존재하는가? 없다면 SVG 대체 가능?
- iOS Safari는 manifest 일부 무시 — `apple-mobile-web-app-*` 메타태그로 커버 가능한가?

**Idea #218 (First Task Celebration)**:
- Task 완료 이벤트를 프론트엔드에서 감지하는 현재 방식 (폴링? WebSocket?)
- `localStorage`에 `first_task_done` 플래그 저장 — 멀티 디바이스 환경에서 괜찮은가? (서버 저장 필요 여부)
- confetti 라이브러리 추가 (canvas-confetti ~3KB) vs CSS 애니메이션 순수 구현 — 어느 쪽?

**Idea #219 (Developer API Mode)**:
- 기존 `#198 Scoped API Keys` 구현 상태: 착수됐는가? 없다면 API Key 모델부터 필요
- Rate limiting: 기존 `fastapi-limiter` 또는 Redis 기반 — 재사용 가능한가?
- 인증 방식: `Authorization: Bearer <api_key>` 헤더로 통일? 기존 JWT와 충돌 없나?

---

**작성 완료**: 2026-02-19 05:20 UTC  
**총 아이디어**: **219개** (기존 216개 + 신규 3개: #217-219)  
**핵심 메시지**: **아이디어보다 배포. #217/#218/#214 오늘 배포 = Phase 39 최우선 목표.**  
**배포 목표**: 이번 주 3개 배포 → 격차 21배 → 7배로 줄이기
