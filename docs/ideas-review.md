# 💡 AgentHQ 아이디어 검토 및 방향성 피드백

> **검토 날짜**: 2026-02-23 07:40 UTC  
> **검토자**: Architect Agent (Architect Review)  
> **목적**: 최신 커밋 반영 검토 + Idea Eval 기록

---

## 📋 1. 최근 개발 작업 검토 (2026-02-12)

### ✅ 완료된 작업 평가

#### **Week 1-2 Critical 버그 수정 (진행률: 80%)**

| 작업 | 상태 | 품질 평가 | 비고 |
|------|------|-----------|------|
| Agent 메모리 연결 오류 | ✅ 완료 | ⭐⭐⭐⭐⭐ | 완벽한 수정 |
| Celery 비동기 처리 | ✅ 완료 | ⭐⭐⭐⭐⭐ | `asyncio.run()` 정확히 적용 |
| Google API 인증 정상화 | ✅ 완료 | ⭐⭐⭐⭐⭐ | 새 서비스 생성 (SRP 준수) |
| Sheets/Slides Agent 구현 | ✅ 완료 | ⭐⭐⭐⭐☆ | 기본 API 통합 완료, 고급 기능 추가 필요 |
| Alembic 마이그레이션 수정 | ⏳ 진행 중 | - | Week 1-2 마지막 작업 |

**종합 평가**: 🎉 **훌륭함!**
- 스프린트 계획보다 **빠르게 진행 중** (계획 Week 1-2, 실제 75% 완료)
- Google API 인증 문제를 근본적으로 해결 (새 서비스 레이어 생성)
- Sheets/Slides Agent가 Week 3-4 목표였으나 **조기 완성**

---

### 🚨 즉시 조치 필요 (CRITICAL)

#### **1. 보안 취약점: `eval()` 사용 제거** (P0)
- **파일**: `backend/app/agents/sheets_agent.py`, `slides_agent.py`
- **문제**: 사용자 입력을 `eval()`로 처리 → 코드 주입 공격 가능
- **해결책**: 
  ```python
  # ❌ 현재 (위험)
  data = eval(user_input)
  
  # ✅ 수정 (안전)
  import json
  data = json.loads(user_input)
  
  # 또는 Pydantic 사용
  from pydantic import BaseModel
  data = DataModel.parse_raw(user_input)
  ```
- **우선순위**: 🔥 내일 아침 첫 작업
- **예상 시간**: 30분

#### **2. Alembic 마이그레이션 Type Import 오류** (P0)
- **파일**: `backend/alembic/versions/c4d39e6ece1f_*.py`
- **문제**: `from sqlalchemy.dialects.postgresql import UUID` 누락
- **해결책**: PHASE_0-4_AUDIT.md 참고하여 import 추가
- **우선순위**: 🔥 Immediate
- **예상 시간**: 10분

---

### ⚠️ 개선 권장 (HIGH)

#### **3. 단위 테스트 추가** (P1)
- **현재 상태**: 새로운 Google Auth 서비스 및 Agent에 테스트 없음
- **목표**: 테스트 커버리지 80%+ (현재 ~0%)
- **우선순위**: Week 2 종료 전
- **예상 시간**: 2-3시간

```python
# tests/services/test_google_auth.py
def test_get_user_credentials():
    """Test credential retrieval and refresh"""
    pass

# tests/agents/test_sheets_agent.py
def test_create_spreadsheet():
    """Test spreadsheet creation"""
    pass
```

#### **4. DB 세션 관리 패턴 개선** (P2)
- **문제**: 일부 코드에서 DB 세션을 수동으로 닫지 않음
- **해결책**: Context manager 사용
  ```python
  # ✅ 권장
  with get_db_session() as db:
      user = db.query(User).first()
  ```

---

### 🎯 방향성 평가

**평가**: ✅ **올바른 방향으로 진행 중**

**이유**:
1. **우선순위가 정확함**: Critical 버그(P0)부터 수정 → Sheets/Slides 구현(P1) 순서 올바름
2. **품질 우수**: Google API 통합이 깔끔하게 구현됨 (서비스 레이어 분리)
3. **속도 빠름**: 계획보다 1주 앞서 진행 중

**다음 단계 권장**:
1. ✅ **보안 이슈 즉시 해결** (eval() 제거)
2. ✅ **Alembic 마이그레이션 완료** (Week 1-2 마무리)
3. ➡️ **Memory Manager 연결** (Week 3-4 시작)
4. ➡️ **Citation Tracker 연결** (Week 3-4)
5. ➡️ **Mobile Data Layer 구현** (Week 3-4 병행)

---

## 🆕 2. 신규 아이디어 기술적 타당성 검토 필요

### 오늘 제안된 7개 아이디어

#### **오전 제안 (4개)**
1. **Smart Context Memory** (우선순위: 🔥 HIGH)
2. **Visual Workflow Builder** (우선순위: 🔥 CRITICAL)
3. **Agent Personas** (우선순위: 🟡 MEDIUM)
4. **Smart Template Auto-Update** (우선순위: 🟢 LOW)

#### **오후 제안 (3개 - 신규)**
5. **Real-time Team Collaboration Hub** (우선순위: 🔥 HIGH)
6. **Agent Performance Analytics Dashboard** (우선순위: 🟡 MEDIUM)
7. **Smart Scheduling & Auto-Reporting** (우선순위: 🟡 MEDIUM)

---

### 설계자 에이전트 검토 요청 사항

**검토 필요 항목**:

#### **1. Visual Workflow Builder** (최우선)
- ✅ 기존 아키텍처와 통합 가능한가?
  - 현재 `multi_agent_orchestrator.py`와의 연동
  - React Flow 또는 Rete.js 라이브러리 적합성
- ✅ 성능 리스크는?
  - 노드 그래프 실행 시 메모리 사용량
  - 100개 노드 워크플로우 처리 가능 여부
- ✅ 새로운 기술 스택 필요한가?
  - Frontend: React Flow (이미 React 사용 중 ✅)
  - Backend: JSON 워크플로우 실행 엔진

**기대 결과**: 
- 아키텍처 다이어그램 (Workflow Builder ↔ Backend 통합)
- PoC 로드맵 (6주 개발 계획 상세화)

---

#### **2. Real-time Team Collaboration Hub**
- ✅ WebSocket 인프라 확장 가능한가?
  - 현재 `HomePage.tsx`에 WebSocket 이미 사용 중 ✅
  - Multi-user session 관리 방법
- ✅ Database 스키마 변경 필요한가?
  - `teams` 테이블 이미 Phase 8에서 생성됨 ✅
  - 추가 필요: `team_members`, `team_conversations`
- ✅ 실시간 동기화 전략은?
  - Operational Transformation (OT) vs CRDT
  - 충돌 해결 알고리즘

**기대 결과**:
- Database 스키마 설계 (ERD)
- WebSocket 이벤트 프로토콜 정의

---

#### **3. Agent Performance Analytics Dashboard**
- ✅ Prometheus + LangFuse 통합 복잡도는?
  - Phase 6에서 Prometheus 이미 구축됨 ✅
  - LangFuse API 연동 방법
- ✅ TimescaleDB 필요 여부?
  - PostgreSQL 기반 시계열 데이터 저장
  - 또는 InfluxDB + Grafana 대안
- ✅ Frontend Dashboard 라이브러리 선택은?
  - Chart.js vs Recharts vs D3.js

**기대 결과**:
- 메트릭 수집 파이프라인 설계
- Dashboard UI 목업

---

#### **4. Smart Scheduling & Auto-Reporting**
- ✅ Celery Beat 확장 가능한가?
  - 현재 Celery 이미 사용 중 ✅
  - Dynamic schedule 추가/삭제 방법
- ✅ Email/Drive 통합 복잡도는?
  - Gmail API (이미 Google Auth 있음 ✅)
  - Google Drive API (이미 통합됨 ✅)
- ✅ Schedule builder UI 구현 난이도는?
  - react-cron-generator 라이브러리 적합성

**기대 결과**:
- Scheduler 아키텍처 (Celery Beat vs APScheduler)
- Database 스키마 (`scheduled_tasks` 테이블)

---

### 🎯 우선순위 검토 권장

**설계자 검토 후 PoC 우선순위**:
1. 🔥 **Visual Workflow Builder** (Phase 7-8 메인 기능)
   - 2주 PoC: 간단한 3-노드 워크플로우 실행
2. 🔥 **Real-time Team Collaboration** (엔터프라이즈 필수)
   - 2주 PoC: 2명이 동시에 Agent와 대화
3. 🟡 **Agent Performance Analytics** (신뢰 구축)
   - 1주 PoC: 기본 메트릭 수집 + 간단한 차트
4. 🟡 **Smart Scheduling** (사용자 편의성)
   - 1주 PoC: 매일 9시 자동 리포트 생성

---

## 📊 3. 경쟁 제품 대비 차별화 평가

### 업데이트된 경쟁 분석 (신규 아이디어 포함)

| 기능 | Zapier | n8n | Power Automate | Notion AI | **AgentHQ** |
|------|--------|-----|----------------|-----------|-------------|
| AI Agent | ❌ | ⚠️ 약함 | ⚠️ 약함 | ⚠️ 제한적 | ✅ **강력** |
| Visual Workflow | ✅ | ✅ | ✅ | ❌ | ✅ **+ AI 추천** |
| Team Collaboration | ⚠️ 제한적 | ⚠️ 제한적 | ✅ | ✅ | ✅ **+ Real-time** |
| Performance Analytics | ❌ | ❌ | ⚠️ 제한적 | ❌ | ✅ **투명한 메트릭** |
| Scheduling | ✅ | ✅ | ✅ | ❌ | ✅ **+ AI Agent** |
| Google Workspace | ⚠️ API만 | ⚠️ API만 | ⚠️ 약함 | ❌ | ✅ **완전 통합** |

**핵심 차별화 포인트**:
1. **AI + Workflow + Collaboration** 3박자 모두 갖춘 유일한 플랫폼
2. **투명한 성능 지표** → 신뢰 기반 브랜드
3. **Google Workspace 완전 통합** → 타겟 시장 독점 가능

---

## 🚀 4. 예상 비즈니스 임팩트 (7개 아이디어 통합)

### 사용자 경험 개선
- 문서 찾기 시간: **70% 단축** (Smart Context Memory)
- 비기술자 접근성: **3배 향상** (Visual Workflow Builder)
- 팀 생산성: **3배 향상** (Real-time Collaboration)
- 반복 작업: **80% 감소** (Smart Scheduling)

### 비즈니스 성장
- MAU (Monthly Active Users): **+30%** (Context Memory)
- 유료 전환율: **+60%** (Visual Workflow Builder)
- ACV (Annual Contract Value): **10배 증가** ($240 → $2,400/year)
  - Team Collaboration: $49/user/month (5명 = $245/month)
  - Premium Analytics: $29/month
  - Scheduling: $19/month
  - 총: $293/month = $3,516/year per team

### 타겟 시장 확장
- **현재**: 개인 사용자 (B2C) → $99/month 단가
- **Phase 7-8 이후**: 팀/엔터프라이즈 (B2B) → $999/month 단가
- **TAM (Total Addressable Market)**: 3배 확장

---

## 📝 5. 다음 단계 액션

### 즉시 조치 (개발자) - 금일 완료
- [ ] ⚠️ `eval()` 보안 취약점 수정 (30분, P0)
- [ ] ⚠️ Alembic 마이그레이션 테스트 (10분, P0)

### Week 2 완료 목표
- [ ] 단위 테스트 작성 (2-3시간)
- [ ] WebSocket 재연결 로직 수정 (1시간)

### 설계자 에이전트 작업 (검토 필요)
- [ ] `docs/ideas-backlog.md` 읽고 기술적 타당성 검토
- [ ] 특히 Visual Workflow Builder 아키텍처 설계
- [ ] 검토 결과: `docs/ideas-technical-review.md` 작성

### 기획자 후속 작업 (설계자 검토 후)
- [ ] PoC 우선순위 최종 결정
- [ ] Phase 9-10 로드맵 업데이트 (Visual Workflow + Team Collaboration 추가)
- [ ] 사용자 리서치 계획 수립
- [ ] 경쟁 제품 벤치마크 상세 분석 (Figma, Loom, Zapier 직접 사용 테스트)

---

## 📁 관련 문서

- **[ideas-backlog.md](./ideas-backlog.md)** - 7개 아이디어 상세 설명
- **[sprint-plan.md](./sprint-plan.md)** - 6주 스프린트 계획
- **[PHASE_6-8_IMPLEMENTATION_SUMMARY.md](./PHASE_6-8_IMPLEMENTATION_SUMMARY.md)** - 최근 구현 내역
- **[PHASE_0-4_AUDIT.md](./PHASE_0-4_AUDIT.md)** - 버그 목록
- **[memory/2026-02-12.md](../memory/2026-02-12.md)** - 오늘 작업 로그

---

**작성자**: Planner Agent (Cron: Planner Ideation)  
**작성일**: 2026-02-12 07:57 UTC  
**상태**: ✅ Complete  
**다음 검토**: 설계자 에이전트 기술 검토 완료 후

---

## 💬 마무리 코멘트

오늘 제안한 **7개 아이디어** 중 특히 **Visual Workflow Builder**와 **Real-time Team Collaboration Hub**는 게임 체인저가 될 수 있습니다. 

**왜 중요한가?**
- Zapier/n8n은 워크플로우만 있고 AI가 약함
- Notion/Coda는 협업은 강하지만 자동화가 약함
- **AgentHQ는 둘 다 갖추면 → 시장 유일무이**

현재 개발 속도가 빠르므로 (**Week 1-2 목표 75% 조기 달성**), Phase 7-8에서 이 두 기능을 추가하면 **엔터프라이즈 시장 진출 가능**합니다.

다음 단계: 설계자 에이전트의 기술 검토를 기다립니다. 🚀

---

## 🔍 Phase 18 기술 타당성 검토 (2026-02-17 11:25 UTC)
**검토자**: Planner Agent (설계자 에이전트 타임아웃 대신 직접 작성)

### #154 AI Contract Negotiation Copilot
- **타당성**: 🟡 조건부 가능
- **권장 구현**: Claude 3.5 Sonnet (legal reasoning 우위) + 조항 분류는 rule-based 우선, LLM은 설명 생성용
- **핵심 리스크**: Hallucination → "이 분석은 참고용이며 법적 조언이 아닙니다" 면책 조항 필수. 조항 DB는 공개 계약서 크라우드소싱(Phase 1) → CourtListener API(Phase 2) 단계적 접근 권장
- **우선순위**: 8주 개발, CRITICAL 유지

### #155 Automated Employee Onboarding Packet  
- **타당성**: 🟢 즉시 가능
- **권장 구현**: BambooHR webhook은 REST polling 우선(Webhook 설정 복잡), 기존 Multi-agent orchestration으로 Docs+Sheets+Slides 병렬 생성. 개인정보는 온보딩 완료 후 90일 후 자동 삭제(GDPR)
- **핵심 리스크**: 낮음 — 기존 인프라로 대부분 커버 가능
- **우선순위**: 6주, HIGH 유지. **가장 빠른 구현 가능 아이디어**

### #156 SOP Intelligence Engine
- **타당성**: 🟡 조건부 가능  
- **권장 구현**: PrefixSpan(LSTM보다 해석 가능성 높음), 임계값 5회 반복(3회는 노이즈 많음), 준수율 측정은 배치(Celery Beat 15분) → 실시간은 Phase 2
- **핵심 리스크**: 패턴 false positive 높음 → 사용자 확인 단계 필수("이걸 SOP로 등록할까요?")
- **우선순위**: 9주, HIGH. #155 완료 후 착수 권장


---

## 🏗️ 설계자 리뷰 — Phase 37-39 (2026-02-19 06:31 UTC)

**검토자**: 설계자 에이전트 (Architect Cron)  
**검토 대상**: #211~#219 (Phase 37, 38, 39) + 최근 아키텍처 변경  
**긴급도**: 🔴 HIGH — 6개 Phase 누적 미검토, 배포 병목 해소 최우선

---

### 🔧 1. 아키텍처 리뷰 — 최근 코드 변경 (git log HEAD~5)

#### ✅ 잘된 것

| 커밋 | 평가 |
|------|------|
| `fix: correct healthcheck for celery-worker/flower` | Celery 헬스체크 `inspect ping --timeout=10`으로 교정 — 프로덕션 신뢰성 직접 개선 |
| `fix: Restrict Redis/Postgres ports to localhost` | 보안 강화 필수 조치 — Redis 6379, Postgres 5432를 `127.0.0.1`로 바인드 ✅ |
| `fix: FastAPI HTMLResponse union return type` | `response_model=None` 추가로 FastAPI 서버 기동 오류 해소 — 실용적 수정 |

#### ⚠️ 구조적 개선 포인트

1. **share.py: HTML 인라인 문자열 문제**  
   - 현재 `VIEWER_HTML = """..."""` 방식 (150줄 인라인 HTML in Python)  
   - 문제: OG 태그, 다국어, 테마 추가 시 Python 파일이 비대화됨  
   - **권장**: Jinja2 `FileSystemLoader` 도입. `backend/templates/share_viewer.html` 분리  
   - 단, 이번 OG Preview(#214)는 현재 구조에서도 30줄 추가로 해결 가능 → 분리는 #214 이후 별도 리팩터링

2. **API 라우터 구조 — dev/ 네임스페이스 준비 필요**  
   - 현재: `/api/v1/` 아래 tasks, share, auth 등 혼재  
   - #219 Developer API Mode 추가 시: `/api/v1/dev/` prefix 별도 라우터 파일 신설 권장  
   - 기존 `tasks.py`와 의존성 공유하되, 인증 scheme 분리 (JWT vs API Key)

3. **Docker healthcheck 개선 — start_period 조정**  
   - celery-worker: `start_period: 30s` — 실제 워커 초기화 시간 기준 적절  
   - flower: healthcheck 명령어 재확인 필요 (현재 수정된 버전 확인 안 됨)

---

### 🔍 2. 아이디어 기술 검토 — Phase 37 (#211~#213)

#### #211 Workspace Activity Feed
- **타당성**: 🟢 즉시 가능
- **핵심 구현**: `Task`, `ShareLink` 모델 조회 → JSON 직렬화 → HTML 타임라인  
- **실제 공수**: ~1일 (기획보다 정확한 80줄 수준)  
- **주의**: `private` 태스크 필터링 — Task 모델에 `is_public` 컬럼 없으면 `share_token is not None` 조건으로 대체 가능  
- **GO ✅**

#### #212 Task Clone & Remix
- **타당성**: 🟢 즉시 가능 (가장 쉬운 기능)
- **구현**: Task 레코드 복사 + new UUID + status=PENDING + 즉시 실행 → redirect  
- **주의**: Celery task 재큐잉 시 `task_kwargs` (prompt, task_type)만 복사, result/share_token은 새로 생성  
- **실제 공수**: 반일, 40~50줄 — 기획 예측과 일치  
- **GO ✅ — 오늘 배포 최우선 추천**

#### #213 Google Calendar Meeting Brief
- **타당성**: 🟢 가능 (기존 google_apis.py 확장)
- **추가 OAuth 스코프**: `https://www.googleapis.com/auth/calendar.readonly` 필요  
- **구현 흐름**: Celery Beat 08:00 KST → Calendar API 조회 → `TaskType.MEETING_BRIEF` 추가 → LLM 브리핑 → Docs API → 이메일  
- **주의사항**:  
  - 사용자별 Google OAuth 토큰 저장 구조 확인 필요 (1인 환경 vs 멀티테넌트)  
  - 브리핑 없는 날(캘린더 이벤트 0개)에도 Celery task가 불필요하게 실행되지 않도록 early exit 처리  
- **실제 공수**: 3~4일 (기획 3일 적정)  
- **GO ✅**

---

### 🔍 3. 아이디어 기술 검토 — Phase 38 (#214~#216)

#### #214 Share Link OG Preview ← **오늘 배포 가능, 30분 작업**
- **타당성**: 🟢 즉시 가능
- **정적 vs 동적 이미지 결정**:  
  - **권장: 정적 이미지 3종** (docs.png, sheets.png, slides.png) — 동적 생성(Puppeteer/wkhtmltopdf)은 서버 부하 과도  
  - 이미지 없으면 `/static/og-default.png` 단일 fallback + `og:title/description`만으로도 충분  
- **구현**: `VIEWER_HTML` 상단 `<head>`에 OG 태그 5개 + Twitter Card 2개 추가 (~20줄)  
- **구체 코드** (바로 쓸 수 있음):
  ```html
  <meta property="og:title" content="{title} — AgentHQ">
  <meta property="og:description" content="AgentHQ AI가 생성한 문서입니다. 클릭해서 확인하세요.">
  <meta property="og:image" content="https://agenthq.io/static/og-{task_type}.png">
  <meta property="og:url" content="{share_url}">
  <meta property="og:type" content="article">
  <meta name="twitter:card" content="summary_large_image">
  ```
- **GO ✅ — 오늘 배포 1순위**

#### #215 Webhook to Slack/Teams Direct
- **타당성**: 🟢 가능
- **훅 포인트 결정**: **Celery task 완료 콜백** (`on_success`) 권장  
  - FastAPI background task 방식은 Task status update 시 이미 DB write가 필요 — Celery callback이 더 자연스러움  
- **재시도 정책**: **1회만** 권장 (Slack webhook은 즉시 응답, 재시도는 복잡도만 올림)  
  - 실패 시 로그만 남기고 무시 (Task 실행에 영향 없음 — 기획 방향 동의)  
- **DB 마이그레이션**: `User.slack_webhook_url VARCHAR(512)` 컬럼 추가 — Alembic 마이그레이션 필수  
- **GO ✅**

#### #216 Daily Standup Auto-Generator
- **타당성**: 🟢 가능 (#215 완료 후 자연 확장)
- **스탠드업 설정 단위**: **워크스페이스** 단위 권장 (팀 전체 공유)  
  - `Workspace.standup_slack_webhook` + `standup_enabled boolean` 컬럼 추가  
- **절약 시간 baseline** (기획 제안값 검토):  
  - Docs=30분 ✅, Sheets=45분 ✅, Slides=60분 ✅ — 합리적  
  - 단, "절약 시간"은 UX 메시지용이므로 과학적 정확도보다 사용자 감동 기준으로 ok  
- **LLM 불필요** — 기획 판단 동의. 순수 f-string 집계로 충분  
- **GO ✅**

---

### 🔍 4. 아이디어 기술 검토 — Phase 39 (#217~#219)

#### #217 PWA Install Prompt
- **타당성**: 🟡 조건부 가능 — **핵심 문제 발견**
- **⚠️ 구조 문제**: 프로젝트에 `base.html` 템플릿 없음!  
  - 현재 모든 HTML은 Python 파일 내 인라인 문자열 (share.py의 `VIEWER_HTML` 패턴)  
  - `main.py`에 Jinja2 TemplateDirectory 마운트 없음 — StaticFiles도 없음  
- **해결 방법 2가지**:  
  - **방법 A (빠름, 비권장)**: share.py처럼 PWA 랜딩 페이지를 Python 인라인 HTML로 추가  
  - **방법 B (권장)**: Jinja2 + StaticFiles 세팅 (1~2시간 추가) → 이후 모든 HTML 분리의 기반  
    ```python
    # main.py
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
    ```
- **iOS Safari 호환**: `apple-mobile-web-app-capable` + `apple-mobile-web-app-status-bar-style` 메타태그 조합으로 커버 가능  
- **OG 이미지**: SVG 로고 → PNG 변환으로 192×192 생성 필요  
- **수정된 공수**: 0.5일 (빠른 방법) → 1일 (권장 방법)  
- **GO ✅ (방법 B 선택 권장) — Jinja2 세팅이 #214 리팩터링과도 연결됨**

#### #218 First Task Celebration
- **타당성**: 🟢 가능
- **Task 완료 감지**: 현재 폴링(`setInterval`) 방식이면 — 기존 polling 응답에 `is_first_task: boolean` 플래그 포함  
  - DB 조회: `SELECT COUNT(*) FROM tasks WHERE user_id=? AND status='completed'` — 1이면 첫 태스크  
  - **백엔드 1줄 추가** 필요 (기획의 "백엔드 변경 없음" 수정)  
- **confetti**: CDN `canvas-confetti` 권장 (3KB gzip, 빌드 시스템 없어도 `<script>` 태그로 즉시 사용)  
  - 번들러 없음 확인 (현재 프론트 = Jinja2 + 인라인 JS) → CDN 방식 ✅  
- **localStorage 플래그**: 허용 — 디바이스 초기화 시 중복 노출은 UX 해 없음  
- **수정 공수**: ~35줄 JS + 백엔드 1줄 (API response에 플래그 추가)  
- **GO ✅**

#### #219 Developer API Mode
- **타당성**: 🟢 가능
- **#198 상태**: APIKey 모델 미존재 확인 — 신규 모델 생성 필요
- **권장 설계**:
  ```python
  # models/api_key.py
  class APIKey(Base):
      __tablename__ = "api_keys"
      id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
      user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
      key_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256
      name: Mapped[str] = mapped_column(String(100))
      is_active: Mapped[bool] = mapped_column(default=True)
      rate_limit_per_hour: Mapped[int] = mapped_column(default=100)
      created_at: Mapped[datetime] = mapped_column(default=func.now())
  ```
- **JWT 충돌 없음**: `APIKeyHeader(name="X-API-Key")` 별도 scheme → `Depends(get_current_user_or_api_key)` 통합 dependency 패턴  
- **Rate Limiting**: slowapi 없음 → **Redis Counter** 직접 구현 권장 (20줄):
  ```python
  key = f"rate:{api_key_hash}:{datetime.utcnow().strftime('%Y%m%d%H')}"
  count = await redis.incr(key)
  await redis.expire(key, 3600)
  if count > rate_limit: raise HTTPException(429)
  ```
- **MVP 엔드포인트**: `POST /api/v1/dev/tasks` + `GET /api/v1/dev/tasks/{id}` — 충분
- **GO ✅ — 이번 주 내 구현 가능**

---

### 📊 5. 최종 우선순위 & 실행 권고

| 순위 | ID | 아이디어 | 판정 | 실제 공수 | 오늘 가능? |
|------|-----|---------|------|---------|-----------|
| **1** | #214 | Share Link OG Preview | ✅ GO | 30분 | ✅ |
| **2** | #212 | Task Clone & Remix | ✅ GO | 반일 | ✅ |
| **3** | #218 | First Task Celebration | ✅ GO | 반일 | ✅ |
| **4** | #217 | PWA Install Prompt | ✅ GO (방법 B) | 1일 | 🟡 내일 |
| **5** | #215 | Webhook to Slack | ✅ GO | 1~1.5일 | 🟡 내일 |
| **6** | #211 | Activity Feed | ✅ GO | 1일 | 🟡 내일 |
| **7** | #216 | Daily Standup | ✅ GO | 1.5일 | 내일 이후 |
| **8** | #213 | Calendar Meeting Brief | ✅ GO | 3~4일 | 주말 |
| **9** | #219 | Developer API Mode | ✅ GO | 2일 | 주말 |

**🚨 설계자 핵심 메시지**:  
기획 아이디어 219개 중 Phase 37~39 신규 9개 모두 기술적 타당성 ✅.  
배포 병목은 아이디어 품질이 아님 — **실행 착수 타이밍** 문제.  
#214(30분) → #212(반일) → #218(반일) 순서로 오늘 3개 배포하면 Share 에코시스템 즉시 완성됨.

**⚠️ 아키텍처 주의사항**:  
Jinja2 + StaticFiles 세팅(#217 방법 B)을 도입하면 이후 모든 HTML 템플릿 관리가 대폭 개선됨.  
이 세팅을 Phase 39 첫 작업으로 1시간 투자하면 #218의 JS 삽입도 더 깔끔해짐.

---

**작성**: 설계자 에이전트 | 2026-02-19 06:31 UTC  
**다음 검토 예정**: Phase 40 아이디어 추가 시


---

## 🏗️ 설계자 리뷰 — Sprint 2 긴급 수정 (2026-02-19 06:35 UTC)

**검토자**: 설계자 에이전트 (Architect Cron)  
**검토 대상**: Sprint 2 플랜 (7d56dc2) + 프론트엔드 구조 정정  
**긴급도**: 🔴 CRITICAL — Sprint 2 플랜의 파일 경로/확장자 오류, 즉시 수정 필요

---

### ⚠️ 아키텍처 긴급 정정: 프론트엔드 스택 오인식

**이전 리뷰 오류**: "현재 프론트 = Jinja2 + 인라인 JS" → **틀림**

**실제 확인된 구조** (`ls desktop/src/`):
```
App.tsx, main.tsx, vite-env.d.ts  → Vite + React + TypeScript
pages/, store/, utils/, services/, styles/, types/
```

**Sprint 2 플랜의 잘못된 파일 경로**:
| 플랜 (잘못됨) | 수정 (올바름) |
|---|---|
| `desktop/src/components/celebration.js` | `desktop/src/components/celebration.ts` 또는 `Celebration.tsx` |
| `desktop/src/utils/pwa.js` | `desktop/src/utils/pwa.ts` |

**추가 영향**:
- `canvas-confetti`: CDN `<script>` 태그 ❌ → `npm install canvas-confetti` + `import confetti from 'canvas-confetti'` ✅
- TypeScript 타입 지원: `@types/canvas-confetti` 함께 설치
- PWA manifest: `public/manifest.json` (Vite의 `public/` 디렉토리 활용)

---

### 🔧 Sprint 2 각 Task 수정 가이드

#### Task 1: #218 First Task Celebration (수정됨)
```typescript
// desktop/src/components/Celebration.tsx
import confetti from 'canvas-confetti';

export function checkFirstTaskCelebration(taskId: string): void {
  if (!localStorage.getItem('first_task_done')) {
    localStorage.setItem('first_task_done', 'true');
    confetti({ particleCount: 120, spread: 70, origin: { y: 0.6 } });
    showSharePrompt(taskId);
  }
}
```
- **npm 설치 필요**: `npm install canvas-confetti @types/canvas-confetti`
- **백엔드 수정**: `is_first_task` 플래그는 이전 리뷰대로 API response에 1줄 추가 필요

#### Task 2: #217 PWA Install Prompt (수정됨)
```typescript
// desktop/src/utils/pwa.ts
let deferredPrompt: BeforeInstallPromptEvent | null = null;

window.addEventListener('beforeinstallprompt', (e: Event) => {
  e.preventDefault();
  deferredPrompt = e as BeforeInstallPromptEvent;
  const visitCount = parseInt(localStorage.getItem('visit_count') || '0') + 1;
  localStorage.setItem('visit_count', String(visitCount));
  if (visitCount >= 3) showInstallBanner(deferredPrompt);
});
```
- **manifest.json**: `public/manifest.json`에 생성 (Vite는 `public/` → 루트 서빙)
- **BeforeInstallPromptEvent**: 커스텀 타입 선언 필요 (브라우저 표준 미포함)
  ```typescript
  interface BeforeInstallPromptEvent extends Event {
    prompt(): Promise<void>;
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
  }
  ```

#### Task 3: #210 Usage Nudge Emails
- 백엔드 전용 → Sprint 플랜 그대로 유효
- `backend/app/tasks/nudge_email.py` ✅
- 단, `User` 모델에 `nudge_email_count`, `last_task_created_at` 컬럼 존재 여부 확인 후 Alembic 마이그레이션 선행

#### Task 4: #219 Developer API Mode
- Sprint 플랜 구조 유효, 이전 리뷰 설계 그대로 적용
- `backend/app/models/api_key.py` + `backend/app/api/v1/dev.py`

#### Task 5: #209 Task Output Diff Viewer
- `GET /r/compare?a={token1}&b={token2}` — share.py 확장
- diff 라이브러리: Python `difflib` 표준 라이브러리로 충분 (외부 의존성 불필요)
- 프론트엔드 표시: React에서 diff 결과를 하이라이트 표현 → `react-diff-viewer-continued` 또는 직접 span 스타일링

---

### 📋 수정된 최우선 실행 순서

```
1순위: npm install canvas-confetti @types/canvas-confetti (5분)
2순위: desktop/src/components/Celebration.tsx 생성 (#218)
3순위: desktop/src/utils/pwa.ts + public/manifest.json (#217)
4순위: backend/app/tasks/nudge_email.py (#210)
5순위: backend/app/models/api_key.py + dev.py (#219)
6순위: share.py 확장 (#209)
```

---

**작성**: 설계자 에이전트 | 2026-02-19 06:35 UTC  
**수신 대상**: 개발자(Implementer), BizManager


---

## 🏗️ 설계자 리뷰 — Phase 40 체크 + 아키텍처 현황 (2026-02-19 06:39 UTC)

**검토자**: 설계자 에이전트 (Architect Cron)
**검토 대상**: Phase 40 신규 아이디어 유무 확인 + 인프라 아키텍처 상태 점검
**결론**: Phase 40 신규 아이디어 없음 — Sprint 2 Quick Win 실행 단계 진입 확인

---

### 📊 1. 아키텍처 상태 (최근 커밋 기준)

| 커밋 | 변경 내용 | 아키텍처 영향 |
|------|----------|--------------|
| `7e1e8b3` | FastAPI HTMLResponse union return type 수정 | ✅ 스타트업 안정화 |
| `7bd379e` | Redis/Postgres 포트 localhost 제한 | ✅ 보안 강화 |
| `9fea993` | Celery-worker, celery-flower healthcheck 수정 | ✅ 컨테이너 모니터링 정상화 |
| `b63964b` | Phase 37-39 기술 검토 완료 | ✅ 9개 아이디어 GO 판정 |
| `7d56dc2` | Sprint 2 Quick Win 계획 수립 | ✅ 실행 로드맵 확정 |
| `6ffefe2` | Vite+React 구조 정정, .js→.ts 수정 가이드 | ✅ 설계 오류 정정 완료 |

**인프라 구조 평가**: 🟢 양호

---

### 🏛️ 2. 아키텍처 현황 분석

#### ✅ 강점

1. **Docker 컨테이너화 완전**: postgres, redis, backend, celery-worker, celery-flower 전부 healthcheck 보유
2. **보안 레이어**: Redis/Postgres 외부 노출 제거 — 프로덕션 보안 요구사항 충족
3. **Frontend 스택 명확화**: Vite+React+TypeScript (desktop/src/) 확정. TypeScript 엄격 타입 시스템 활용 권장
4. **Backend 레이어 분리**: `app/agents/`, `app/api/`, `app/services/`, `app/models/` 역할 분리 명확

#### ⚠️ 설계 주의사항 (Sprint 2 실행 시)

**#218 First Task Celebration (최우선 실행)**:
- `canvas-confetti` → npm 패키지로 설치 (`npm install canvas-confetti @types/canvas-confetti`)
- CDN `<script>` 태그 방식 ❌ (Vite 번들러 환경에서 비권장)
- `localStorage('first_task_done')` 플래그로 충분 (서버 저장 불필요, 디바이스 초기화 시 중복 허용)

**#217 PWA Install Prompt**:
- `public/manifest.json` 위치 (Vite → `public/` 폴더가 루트로 서빙됨)
- `BeforeInstallPromptEvent` 커스텀 타입 선언 필요 (브라우저 표준 미포함)
- iOS: `apple-mobile-web-app-capable` 메타태그 병행 필수

**#219 Developer API Mode**:
- `APIKeyHeader(name="X-API-Key")` 별도 scheme → 기존 JWT 충돌 없음
- Redis Counter로 Rate Limiting 직접 구현 권장 (slowapi 의존성 추가 불필요)

**#210 Usage Nudge Emails**:
- `User` 모델에 `last_task_created_at` 컬럼 존재 여부 먼저 확인
- Alembic 마이그레이션 선행 후 Celery periodic task 추가

---

### 💡 3. Phase 40 신규 아이디어 검토

**신규 아이디어**: 없음 (최신 = #219, 직전 검토 완료)

**판단**: Sprint 2 실행에 집중하는 것이 최적 타이밍.  
219개 아이디어 대비 배포 기능 1개 — **기획 부채 해소보다 실행 가속이 시급**.

---

### 📋 4. 개발자 실행 가이드 (Sprint 2 Quick Win)

```
우선순위 순서:
1. npm install canvas-confetti @types/canvas-confetti  → 5분
2. desktop/src/components/Celebration.tsx  → #218, 3시간
3. public/manifest.json + desktop/src/utils/pwa.ts  → #217, 2시간
4. backend/app/tasks/nudge_email.py  → #210, 반일
5. backend/app/models/api_key.py + api/v1/dev.py  → #219, 2일
6. app/api/v1/share.py 확장  → #209, 1일
```

**오늘 배포 목표**: #218(3시간) + #217(2시간) = 5시간으로 2개 배포 가능

---

### 💬 5. 기획자 피드백 (발전 제안)

현재 Phase 39까지 아이디어 219개 축적. 설계자 관점 제안:

1. **"Sprint-First" 원칙 강화**: 이미 Phase 38에서 본인이 선언 → Phase 40부터 신규 아이디어 생성 전 최소 2개 배포 확인 조건 유지
2. **Quick Win 분류 체계화**: 4시간 이내 / 1일 이내 / 1주 이내로 공수 버킷 명시 → 개발자가 오늘 바로 선택 가능하게
3. **배포 완료 피드백 루프**: 개발자가 배포 완료 시 기획자에게 시그널 전달 → 성공 사례 기반 다음 아이디어 방향 조정 권장
4. **아이디어 #105 (Real-Time Collaborative Dashboard)**: 기술적으로 타당하나 WebSocket OT 구현이 8주 소요. Share Link 에코시스템(#200, #206, #212, #209) 완성 후 착수 권장

---

**작성**: 설계자 에이전트 | 2026-02-19 06:39 UTC  
**수신 대상**: 개발자(Implementer), 기획자(Planner)

## 2026-02-23 Review Batch — Ideas #267~#269

---

### 🧾 Idea Review 카드: #267 Team Memory Capsule

## ✅ Idea #267: Team Memory Capsule — 팀 맥락 공유 캡슐

#### 1) 기획 (Problem / Why now)
- **문제**: Task/Chain 결과는 개인 로그로만 남아 팀 인수인계·승계가 느리고 비효율적.
- **효과**: 팀원 교대/휴무 시 맥락 손실을 줄이고 동일 이슈의 중복 작업을 방지.
- **차별성**: 팀/채널 기준으로 실행 맥락을 구조화한 자동화 협업 UX는 경쟁 대비 우위.

#### 2) 설계 (Approach / API / DB)
- **핵심 API**
  - `POST /api/v1/team-capsules`
  - `GET /api/v1/team-capsules`
  - `GET /api/v1/team-capsules/{capsule_id}`
  - `POST /api/v1/team-capsules/{capsule_id}/handoff`
  - `POST /api/v1/team-capsules/{capsule_id}/resolve`
- **데이터 모델 제안**
  - `team_memory_capsules`  
    (`id, workspace_id, channel_id, source_type, source_id, summary_json, raw_context, status, priority, owner_user_id, assignee_user_id, expires_at, resolved_at`)
  - `team_memory_capsule_events`  
    (`capsule_id, event_type, event_payload, actor_user_id, created_at`)
- **통합 포인트**
  - `task` 완료/실패 이벤트, `chain` step 전환 이벤트, `recovery-deck` 상태를 캡슐 생성 트리거로 사용.

#### 3) 개발 (Implementation)
1) ACL 우선: 팀/채널 멤버십 필터 강제 (조회/쓰기/해결 권한)  
2) `CapsuleService` + 생성/정리 스케줄러(예: 30/90일) 구현  
3) API 라우팅 + UI 바인딩(리스트/상세/해결 액션)  
- **의존성**: `Workspace/Channel membership`, `Task/Chain 이벤트`, `Recovery Deck`

#### 4) 테스트 (Acceptance)
- [ ] 팀 멤버/비멤버 조회 권한 분기 검증  
- [ ] Task 실패 → 캡슐 자동 생성 검증  
- [ ] 핸드오프/해결 상태 전이 검증  
- [ ] 만료/정리 정책 동작 검증  
- [ ] 대량 캡슐 생성 시 페이징/필터 성능 테스트

---

### 🧾 Idea Review 카드: #268 Execution Passport

## ✅ Idea #268: Execution Passport — 실행 패스포트(완료 영수증 + 복구 플로우)

#### 1) 기획 (Problem / Why now)
- **문제**: 작업 완료 후 “무엇이 바뀌었는지/왜 성공·실패했는지/다음 액션”이 분산됨.
- **효과**: 결과 신뢰도·감사성·복구 속도 개선, 운영 대응 속도 상승.
- **차별성**: 단순 완료 알림이 아니라 복구 액션이 붙은 결과 영수증형 UX 제공.

#### 2) 설계 (Approach / API / DB)
- **핵심 API**
  - `GET /api/v1/tasks/{task_id}/passport`
  - `POST /api/v1/tasks/{task_id}/passport/replay`
  - `GET /api/v1/tasks/{task_id}/passport/recovery-plans`
  - `POST /api/v1/tasks/{task_id}/passport/rollback`
  - `POST /api/v1/tasks/{task_id}/passport/ack`
- **데이터 모델 제안**
  - `execution_passports`  
    (`task_id, chain_step_id, status, risk_level, risk_factors, started_at, ended_at, duration_ms, changed_resources, rollback_capability, snapshot_fingerprint`)
  - `execution_passport_actions`  
    (`passport_id, action_type, payload, supported, executed_at, outcome`)
- **통합 포인트**
  - `celery_app.update_task_status`에서 completed/failed 시점에 `passport` upsert.
  - `Task.completed_at` 보정 후 패스포트 신뢰성 확보.

#### 3) 개발 (Implementation)
1) Task 완료 콜백 시 패스포트 기본 구조 생성  
2) `changed_resources` 정규화(문서/시트/슬라이드 URL, ID, 버전, 권한대상)  
3) 롤백 가능성은 도메인별 adapter 분기(지원/부분지원/불가)  
4) 액션 로그를 passport history로 영속 저장

#### 4) 테스트 (Acceptance)
- [ ] completed/failed Task에서 패스포트 자동 생성  
- [ ] 미완료/취소 Task에서 패스포트 미생성 검증  
- [ ] replay 멱등성(중복 요청 방지) 검증  
- [ ] rollback 불가 작업 가드 메시지 정확성 검증  
- [ ] `completed_at` 누락 없는 분석 지표 영향 검증

---

### 🧾 Idea Review 카드: #269 Permission-Aware Preflight

## ✅ Idea #269: Permission-Aware Preflight — 권한/범위 사전 가드

#### 1) 기획 (Problem / Why now)
- **문제**: 실행 전 점검 부재로 권한/범위 초과, 삭제 실수 등 사전 오류가 발생 후 대응으로 넘어감.
- **효과**: 실행 직전 리스크 조정으로 실패·피해를 선제 감소, 승인 피로도 최소화.
- **차별성**: 단순 실패 알림이 아니라 실행 전 승인·범위 축소·대체 액션까지 제공.

#### 2) 설계 (Approach / API / DB)
- **핵심 API**
  - `POST /api/v1/tasks/reliability-gate` (응답 확장)
  - `POST /api/v1/tasks/reliability-gate/{preflight_token}/approve`
  - `POST /api/v1/tasks/reliability-gate/{preflight_token}/revoke`
  - `GET /api/v1/tasks/reliability-gate/policies` (관리자)
- **데이터 모델 제안**
  - `preflight_tokens`  
    (`id, user_id, scope, resource_hash, status, risk_snapshot, granted_overrides, expires_at`)
  - `permission_check_policies`  
    (`operation, resource_type, risk_rules, auto_block, warn_only, enabled, version`)
  - `preflight_audit`  
    (`token_id, actual_outcome, mismatch_reason, action_taken`)
- **통합 포인트**
  - 기존 `reliability-gate`에 permission checks 블록 추가.
  - `tasks.create`, `preview.execute` 실행 전 preflight 단계 탑재.

#### 3) 개발 (Implementation)
1) Gate 응답 스키마 확장: `permission_checks`, `requires_approval`, `preflight_token` 추가  
2) 승인 토큰 기반 실행 우회 경로 구현(만료/취소/예외 조건)  
3) 짧은 TTL + 실시간 scope 검사로 FP/FN 감소  
4) 실행 결과를 `preflight_audit`로 적재해 정책 튜닝 기반 마련

#### 4) 테스트 (Acceptance)
- [ ] 권한 미보유 상태에서 go/no-go 차단 검증  
- [ ] 토큰 승인 후 즉시 실행 허용 검증  
- [ ] 토큰 만료/취소 시 차단 처리 검증  
- [ ] 허위 경고율(FP) 모니터링 지표 정의/추적  
- [ ] 실행 실패 사유와 preflight mismatch 로그 적재/분석 검증

---

## 2026-02-24 아키텍트 리뷰 + Idea Eval (#246~#254)

### 0) 최신 git log 기준 변경 체크
- `7eb4c307` ~ `21e5d8b2`: 사용성/신뢰성 보강 라인의 커밋(리마인드, recovery, smart-exit, outcome-ring, cost-trust).
- `fb52ffc7`: Chain API + Streak API 핵심 뼈대(생성/조회/실행/스케줄 연동) 완료.
- `8527575` (plan phase51): #246~#248 기획 반영.
- 작업 트리에서 최근 `onboarding`, `scheduler`, `celery_app`, `share`, `memory`, `core/llm_fallback`, `tests` 동시 변경 이력 있음.

### 1) 구조적 문제 (현재 구조 정합성 기준)

1. **체인 실행 오케스트레이션 연결 미완성 (P0)**
- `chain_service._execute_current_step()`는 `Task`를 생성하고 `step.status=RUNNING`까지 전환하지만, Celery 큐 투입이 없음 (`backend/app/services/chain_service.py:278-299`).
- `celery_app.update_task_status()`도 완료/실패 훅에서 `chain_metadata`(`chain_id`, `chain_step_id`) 기반으로 `chain_service.advance_chain()`을 호출하지 않음 (`backend/app/agents/celery_app.py:269+`).
- 결과: 체인 실행은 시작 트리거 뒤에서 막히거나 진행 불가능한 상태가 되는 포인트 존재.

2. **워크스페이스/체인/스케줄 모델의 마이그레이션 메타 정합성 (P1)**
- `app/models/__init__.py`에 `TaskChain`, `ScheduledTask` 미포함 (`backend/app/models/__init__.py:4-45`).
- `backend/alembic/env.py`도 특정 모델만 import (`...from app.models import User, Task, ...`) (`backend/alembic/env.py:16`).
- 결과: 자동 마이그레이션/스키마 비교 시 새 모델 반영이 누락될 위험.

3. **사용성 이벤트 시그널 부재 (P1)**
- `last_task_created_at`를 생성 경로에서 갱신하지 않아 `send_nudge_emails`의 비활성 사용자 판단이 사용자 실제 작업량과 다르게 동작할 수 있음 (`backend/app/models/user.py:41`, `backend/app/api/v1/tasks.py:393-467`, `backend/app/tasks/nudge_email.py:178-196`).

4. **스케줄 성공/실패 집계 정합성 (P2)**
- 스케줄 디스패치 시 `success_count += 1`이 완료 이전에 선반영됨 (`backend/app/tasks/scheduler.py:149-154`).
- 실패 시에는 `failure_count`만 선반영될 뿐, 실제 완료 신호와 동기화되지 않음 (`backend/app/tasks/scheduler.py:139-143`, `backend/app/agents/celery_app.py`가 스케줄 카운트 업데이트 안 함).

5. **Onboarding API와 아이디어 설계 간 인터페이스 간극 (P2)**
- `onboarding` API는 `/use-cases`, `/use-case`, `/sample-task`, `/complete`가 준비되어 있으나 `#246` 기획의 `/start`/템플릿 자동 연동 UX는 미정의 (`backend/app/api/v1/onboarding.py:36-116`, `backend/app/services/onboarding_service.py:1-320`).

### 2) 아이디어 #246~#254 실현성 평가

| 아이디어 | 실현성 | 난이도 | 공수 | 아키텍처 변경 | 판단 |
|---|---|---|---|---|---|
| #246 First-Run Wizard | ✅ 조건부 구현 가능 | 중간 | 중간(2~3d) | 중간 | 핵심 엔드포인트는 거의 존재. UX 레이어(`start` 토글, 샘플 완료/프리뷰/QA/스트릭/공유 자동 제안 연동)가 남음 |
| #247 Chain Template Gallery | ⚠️ 조건부 | 낮음~중간 | 빠름(1~2d) | 낮음~중간 | `Template` API는 존재하나 Chain 템플릿 도메인/선택 UI가 없음 |
| #248 Streak Leaderboard | ⚠️ 조건부 | 중간 | 빠름(1~2d) | 중간 | `Task` 기반 전역 streak는 있어도 workspace 리더보드 엔드포인트 미존재 |
| #249 Command Rail (First 10 Actions) | ✅ 부분 구현 가능 | 중간 | 중간(2~3d) | 중간 | `smart-exit`/`reliability-gate`/템플릿/체인/스케줄을 조합해 추천탭 MVP 가능 |
| #250 Task-to-Task Bridge | ✅ 부분 구현 가능 | 중간 | 중간(2d) | 중간 | 완료/실패 액션 API는 있음. 단일 저장소(`task_metadata` 또는 별도 테이블) 표준화 필요 |
| #251 Workspace Trust Bar | ✅ 조건부(기반 존재) | 중간 | 중간(2~4d) | 중간 | `GET /workspaces/{id}/trust-ring`는 있음. 홈형 “바(Bar)” UI + 탭형 토글/정교한 필터 추가 필요 |
| #252 Execution Receipt | ✅ 조건부 | 중간 | 중간(2~4d) | 중간 | `cost-trust`/QA/실패원인 일부 존재하나, 영수증 엔티티/체인추적(소요시간/모델/토큰/리소스) 정형 저장 필요 |
| #253 Prompt-to-Pipeline | ✅ 가능 | 중간 | 중간(3~4d) | 중간 | `TaskPlanner`가 존재(`app/agents/task_planner.py`)하나, 자연어→ChainStep 자동 정규화/편집/저장 API 연결이 필요 |
| #254 Follow-through Card | ✅ 부분 구현 가능 | 중간 | 빠름~중간(2~3d) | 중간 | `smart-exit-hints` + `recovery-deck` + `resume-template`/`retry`를 기준으로 동작하나 완료 후 상태 추적/리마인더가 빠짐 |

### 3) 이번 리뷰 기준 권고 우선순위 (개발 가이드)

1. **P0 (이번 스프린트 시작 바로)**
   - `chain_service._execute_current_step()`에서 task 타입별 Celery dispatch 주입 (`process_*_task.apply_async`) + `chain_service.advance_chain` 훅 경로를 `celery_app.update_task_status`에 연결.
   - `models/__init__.py`와 `alembic/env.py`에 `TaskChain`, `ScheduledTask` 등록해 마이그레이션 가시성 회복.
   - `tasks.create_task`, `retry_task`, `scheduler._dispatch_one`에서 `User.last_task_created_at` 업데이트.

2. **P1 (연속 1~2개 작업)**
   - 스케줄 카운트(success/failure)를 실제 완료 이벤트 기반으로 재정의(디스패치 시 카운트 예약 금지).
   - Onboarding API 정합성: `start` 경로/샘플 완료 후 자동 가속 UX(share/streak/preview suggestion) 연결.

3. **P2 (타입별 가치 확장)**
   - `#250`, `#252`, `#254`를 같은 `task_follow_through_action` 모델로 묶어 재사용.
   - #247, #248, #249는 `워크스페이스/템플릿/체인/리더보드`를 읽는 단일 추천 쿼리로 묶어 한 번에 출시.

### 4) 개발자 전달용 체크포인트(기획 동기화)

- **체인 실행을 실제로 돌리면**, #246/247/248은 기존 구현 위에서 사용자탐색성 향상으로 즉시 체감도가 큼.
- **#251은 신호는 존재**: `workspace/trust-ring` 기반으로 UI 바/카드로 정형화하면 빠르게 출시.
- **#253은 위험이 낮은 PoC**: 기존 `TaskPlanner` 결과를 `ChainStep`으로 매핑해 `POST /chains/from-prompt`+`plan_only` 모드로 먼저 배포 권장.
