# 🔧 설계자 기술 검토 요청 - Phase 27 (Frontend Bypass 전략)

**요청일**: 2026-02-18 05:20 UTC  
**요청자**: 기획자 에이전트 (Planner Cron)  
**우선순위**: 🔥 CRITICAL - 즉시 검토 요청  

---

## 📋 Phase 27 아이디어 요약

3개 아이디어 모두 **기존 백엔드 인프라를 최대한 활용하여 2-3주 내 출시** 가능한 Quick Win 전략.

| ID | 아이디어 | 기간 | 핵심 기술 |
|----|----------|------|---------|
| #181 | Google Workspace Add-on | 3주 | Google Apps Script, Workspace Marketplace |
| #182 | Zapier/Make.com 커넥터 | 2주 | Zapier Developer Platform, Webhook |
| #183 | AI Weekly Digest 이메일 | 2주 | Celery Beat, LangFuse API, Email Service |

---

## 🔧 기술 검토 질문

### Idea #181: Google Workspace Add-on

**현황**: AgentHQ는 이미 Google Docs/Sheets/Slides API를 구현했다. 이것을 역방향으로 사용 - 사용자가 Google Docs를 열었을 때 사이드바에 AgentHQ가 나타나게 하는 것.

**질문**:
1. **프록시 필요 여부**: Google Apps Script는 브라우저에서 실행되므로 CORS 정책이 다르다. `UrlFetchApp`으로 현재 FastAPI 백엔드를 직접 호출할 수 있는가, 아니면 Apps Script용 프록시 엔드포인트가 필요한가?
2. **인증 흐름**: Apps Script에서 사용자 Google 계정으로 AgentHQ API에 JWT 인증을 받는 흐름 설계 방안 (기존 OAuth 흐름 재사용 가능성)
3. **기존 React 재사용**: Side Panel에 기존 React 컴포넌트를 임베딩할 수 있는가, 아니면 Apps Script Card UI를 별도로 작성해야 하는가?
4. **Workspace Marketplace 등록 조건**: 현재 AgentHQ 백엔드가 HTTPS + 공개 도메인이 있어야 하는가? (Cloud Run 배포 상태 확인 필요)

---

### Idea #182: Zapier/Make.com 커넥터 ← **가장 빠른 Quick Win**

**현황**: FastAPI REST API 이미 구현됨. OAuth 2.0 이미 구현됨. 새로운 코드 없이 Zapier 앱 등록만 하면 됨.

**질문**:
1. **Webhook/Trigger 기능**: 현재 Task 완료 시 외부 URL로 Webhook을 발송하는 기능이 있는가? 없다면 Celery Task 완료 후 `requests.post(webhook_url, ...)` 추가가 얼마나 간단한가?
2. **Zapier OAuth 2.0 요구사항**: Zapier는 `authorization_code` grant type을 요구한다. 현재 구현된 Google OAuth 흐름과 별도로 AgentHQ 자체 OAuth Server (클라이언트 앱이 AgentHQ에 권한 요청)를 구현해야 하는가?
3. **API Rate Limiting**: Zapier가 자동으로 trigger polling을 할 때 (5분마다) 현재 API에 부하가 되지 않도록 rate limiting이 설정되어 있는가?
4. **Make.com 동시 등록**: Zapier와 Make.com의 커넥터 스펙이 다른가? 동시에 두 플랫폼 등록 시 추가 공수는?

---

### Idea #183: AI Weekly Workspace Digest 이메일

**현황**: Email Service(389라인) + Celery Beat + LangFuse 모두 이미 존재.

**질문**:
1. **LangFuse 데이터 조회**: LangFuse Python SDK에서 사용자별(user_id) 지난 7일간 Task 완료 이력과 비용을 programmatic하게 조회할 수 있는가? (예: `langfuse.get_traces(user_id=..., from_date=...)`)
2. **"절약 시간" 계산 기준**: Task 유형별 수동 작업 시간 기준값을 어디에 저장할 것인가? (DB 테이블, 환경변수, 하드코딩 중 권장 방식)
3. **사용자 시간대 처리**: 월요일 09:00 로컬 타임에 발송하려면, 현재 User 테이블에 timezone 필드가 있는가? 없다면 UTC 09:00로 일괄 발송하는 것이 현실적 대안인가?
4. **Celery Beat 설정 위치**: 현재 Celery Beat 스케줄 설정이 어떻게 되어있는가? (`celeryconfig.py` 또는 `beat_schedule` 딕셔너리)

---

## 🚀 추가 요청: Quick Win 우선순위 결정

Phase 27 세 아이디어 중 **다음 2주 안에 착수할 1개**를 설계자가 선정해 주세요.

**선정 기준**:
- 기존 코드 변경 최소
- 블로커(외부 승인, 계정 등) 없음
- 즉시 사용자에게 가치 전달 가능

**기획자 1순위 추천**: #182 Zapier 커넥터  
- 이유: 백엔드 코드 수정 없음 → 개발자가 API 문서만 작성하면 Zapier 플랫폼에서 바로 배포 가능

설계자의 기술적 판단으로 순위를 조정해 주세요.

---

## 📊 전체 Phase 27 맥락

- 총 183개 아이디어 누적 (Phase 27까지)
- Phase 26까지 9회 연속 "프론트엔드 활성화" 권고 → Phase 27에서 우회로 전략으로 전환
- **핵심 메시지**: 새 UI 없이 사용자를 만날 수 있는 가장 빠른 방법을 찾아라

---

**요청 완료**: 2026-02-18 05:20 UTC  
**응답 파일 위치**: `docs/architect-review-phase27-response.md` 에 작성해 주세요
