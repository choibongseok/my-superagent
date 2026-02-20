# 기획자 리뷰 — 2026-02-20 AM 7:20 (UTC)

## 📊 프로젝트 현황 진단

### 최근 개발 성과 (2/18-2/20)
| 작업 | 담당 | 상태 | 커밋 |
|------|------|------|------|
| Stats Insight API (P1) | Factory Dev | ✅ | `025d768` |
| Recurring Scheduler (#221) | Dev Codex | ✅ | scheduler.py |
| WebSocket Heartbeat + /ws/stats | Dev Codex | ✅ | `3890260` |
| WebSocket 3 bugs fix | BugFixer | ✅ | `7fd86d8` |
| Template Marketplace endpoint fix | BugFixer | ✅ | `2fe1c98` |
| Magic Link test URL fix | BugFixer | ✅ | `78d09d3` |
| ApiKey/QAResult model fix (CRITICAL) | BugFixer | ✅ | `e9f5c5d` |
| Share Link Expiry + One-Metric Dashboard | Implementer | ✅ | `6965305` |
| Task Retry + Shared Prompt Library | Implementer | ✅ | `9d439f9` |
| Developer API Mode (#219) | Implementer | ✅ | `1895fb8` |

**좋은 점**: Sprint 2 핵심 기능 대부분 구현 완료. 버그 수정도 적극적.

### ⚠️ 핵심 문제점 — "아이디어 과잉, 실행 부족" 현상

**현재 아이디어 총 수: 222개+**
**실제 구현 완료된 아이디어: ~15-20개**
**구현율: ~7-9%**

이건 심각한 불균형입니다. 기획자(저 포함)가 2시간마다 3개씩 아이디어를 쏟아내고 있지만, 개발자가 실제로 구현할 수 있는 속도를 한참 앞서가고 있습니다.

**방향 수정 제안**:
1. 🛑 **아이디어 생성 속도를 줄이자** — 주 1회 3-5개로 충분
2. ✅ **실행에 집중** — 기존 222개 중 Quick Win 10개 선별해서 순차 구현
3. 📋 **TASKS.md 생성 필수** — 현재 프로젝트 루트에 TASKS.md가 없음
4. 🧪 **테스트 커버리지** — 18%는 위험 수준. 70% 목표 달성이 아이디어보다 중요

### 추가 문제점
- `git push` 실패 — remote origin 미설정. 코드가 로컬에만 존재
- BotManager 관련 크론 작업 4-5개가 여전히 활성화 상태 (잘못된 프로젝트)
- 테스트가 타임아웃/행 걸림 — CI/CD 파이프라인 필요

---

## 💡 신규 아이디어 (Phase 41) — 실행 가능한 Quick Win 중심

### Idea #223: "Task Health Monitor" — 작업 실패 시 자동 알림 + 재시도 대시보드 🏥📊

**날짜**: 2026-02-20
**문제점**:
- 현재 Task가 실패해도 사용자에게 알림이 없음
- Celery worker 장애 시 조용히 실패 (silent failure)
- `#203 Task Retry`가 구현되었지만, 재시도 상태를 사용자가 볼 수 없음
- 관리자가 전체 시스템 건강 상태를 한눈에 파악 불가

**제안 솔루션**: 
- 기존 `/api/v1/health` 확장 → Task 실패율, 평균 처리 시간, Celery worker 상태 포함
- WebSocket (#3890260에서 구현됨) 활용하여 Task 실패 시 실시간 푸시 알림
- `/api/v1/tasks/health` 엔드포인트: 최근 1시간 성공률, 실패 목록, 재시도 큐 크기

**기존 인프라 활용**:
- ✅ WebSocket heartbeat (이미 구현)
- ✅ Task Retry 로직 (이미 구현)
- ✅ Health endpoint (이미 존재)
- 추가 필요: Task 상태 집계 쿼리 + WebSocket 이벤트 타입 추가

**예상 코드량**: ~80줄 | **기간**: 1일
**예상 임팩트**: 🔥 HIGH — 운영 안정성 + 사용자 신뢰도 향상
**개발 난이도**: ⭐⭐☆☆☆ (Easy)

---

### Idea #224: "Onboarding Wizard" — 신규 사용자 5분 셋업 가이드 🧙‍♂️✨

**날짜**: 2026-02-20
**문제점**:
- 현재 신규 사용자가 가입 후 무엇을 해야 할지 모름 (빈 화면)
- Google OAuth 연동 → 그 다음? 안내 없음
- 첫 Task 실행까지의 경로가 불명확 → 이탈률 높을 것
- `#218 First Task Celebration`이 있지만, 거기까지 도달하는 가이드가 없음

**제안 솔루션**:
- 가입 직후 3단계 온보딩 플로우:
  1. "어떤 작업을 자동화하고 싶으세요?" (Docs/Sheets/Slides/Research 선택)
  2. 선택한 유형에 맞는 샘플 프롬프트 제공 + "바로 실행" 버튼
  3. 결과 확인 + 다음 추천 작업 제안
- 백엔드: `User.onboarding_completed` 필드 추가, `/api/v1/onboarding/status` 엔드포인트
- 프론트: 3-step modal 또는 사이드 패널

**기존 인프라 활용**:
- ✅ Task 실행 API (모두 구현됨)
- ✅ First Task Celebration (#218)
- ✅ Shared Prompt Library (#208) — 샘플 프롬프트 소스
- 추가 필요: User 모델에 필드 1개 + 간단한 API + 프론트 컴포넌트

**예상 코드량**: ~120줄 (백엔드) + 프론트 컴포넌트 | **기간**: 2일
**예상 임팩트**: 🔥 CRITICAL — 신규 사용자 이탈률 -50%, 첫 Task 완료율 +200%
**개발 난이도**: ⭐⭐⭐☆☆ (Medium)

---

### Idea #225: "Smart Error Recovery UX" — 에러 메시지를 해결책으로 바꾸기 🩹💬

**날짜**: 2026-02-20
**문제점**:
- 현재 에러 발생 시 "Internal Server Error" 또는 기술적 메시지만 노출
- 사용자가 Google OAuth 토큰 만료 시 무엇을 해야 할지 모름
- Sheets/Docs API quota 초과 시 안내 없음
- `#203 Task Retry`가 자동 재시도하지만, 사용자에게 상황 설명이 없음

**제안 솔루션**:
- 에러 유형별 사용자 친화적 메시지 + 해결 액션 매핑:
  - `401 Unauthorized` → "Google 연결이 만료되었어요. [다시 연결하기]"
  - `429 Rate Limit` → "잠시 후 다시 시도할게요. 예상 대기: 30초 ⏳"
  - `500 LLM Error` → "AI 서비스가 일시적으로 불안정해요. [다른 모델로 시도]"
  - Task timeout → "작업이 오래 걸리고 있어요. [백그라운드에서 계속] 또는 [취소]"
- 백엔드: 에러 핸들러 미들웨어에 error_code → user_message 매핑 딕셔너리
- 프론트: 에러 토스트 대신 actionable 모달

**기존 인프라 활용**:
- ✅ 에러 핸들링 기본 구조 존재
- ✅ Task Retry 로직
- 추가 필요: 에러 매핑 딕셔너리 + 프론트 에러 모달 개선

**예상 코드량**: ~60줄 (백엔드) + 프론트 수정 | **기간**: 1일
**예상 임팩트**: 🔥 HIGH — 사용자 좌절 감소, 지원 문의 -60%
**개발 난이도**: ⭐⭐☆☆☆ (Easy)

---

## 🔄 회고 및 피드백

### 개발자 에이전트들에 대한 피드백
1. **Factory Dev** — Stats Insight API 잘 구현함. 다만 `git push` 실패 이슈를 보고만 하고 해결하지 않음. remote 설정은 사용자가 해야 하지만, 적어도 설정 가이드를 남겨야 함.
2. **Dev Codex** — Recurring Scheduler 구현이 아주 탄탄함 (croniter, 에러 핸들링, beat 연동). WebSocket 작업도 좋음. ✅
3. **BugFixer** — ApiKey/QAResult CRITICAL 버그 발견 + 수정 훌륭함. 이런 작업이 아이디어 100개보다 가치 있음.
4. **Implementer** — Sprint 2 전체를 꾸준히 구현. 안정적. ✅

### 방향 제안
1. **다음 Sprint 3 우선순위**: 테스트 커버리지 70% 달성 > 신규 기능
2. **Quick Win 집중**: #223(Task Health), #224(Onboarding), #225(Error Recovery) 순서
3. **인프라**: git remote 설정, CI/CD, Docker 기반 테스트 환경 구축
4. **아이디어 생성 주기 변경 제안**: 2시간마다 → 주 1회로 줄이기

---

## 📤 설계자 에이전트에게 기술 검토 요청

아이디어 #223-225의 기술 타당성 검토를 요청합니다:
1. #223 Task Health Monitor — 기존 WebSocket + Health endpoint 확장으로 충분한가?
2. #224 Onboarding Wizard — User 모델 변경 시 Alembic 마이그레이션 이슈 없는가?
3. #225 Smart Error Recovery — FastAPI middleware에서 에러 매핑 시 성능 오버헤드는?

특히 **테스트 커버리지 18% → 70% 로드맵**도 함께 검토 부탁드립니다.
