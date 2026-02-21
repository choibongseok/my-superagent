# 📋 기획자 에이전트 Phase 47 — 전략 전환 리뷰 + 사용자 접점 아이디어 2개 (2026-02-21 07:20 UTC)

> **Phase 47 핵심 메시지**: 🎯 **"만드는 것을 멈추고, 전달하는 것을 시작하라"**
>
> **배포 현황**: 최근 72시간 배포 4건 (#234, #232, #225, #230) + Streaks 구현 중
> **총 아이디어**: 238개 (기존 236 + 신규 2: #237-238)
> **아이디어 모라토리엄**: 계속 존중. "사용자 접점" 카테고리 아이디어 2개만 예외 추가.

---

## 🔍 최근 개발/설계 방향성 평가: ⭐⭐⭐⭐½

### 🎉 축하할 것들 (Phase 46 이후 변화)

1. **🔥 git remote 설정 완료!**
   - 10회 이상 CRITICAL로 권고했던 이슈가 드디어 해결: `origin → github.com/choibongseok/my-superagent.git`
   - 다만 현재 브랜치(`feat/score-stabilization-20260211`)가 upstream 미설정 → `git push --set-upstream origin` 필요
   - **이것만으로도 Phase 47의 최대 성과**

2. **Productivity Streaks & Achievements 구현 중 (미커밋)**
   - streak_service.py: 496줄 — 일일 스트릭, 마일스톤 배지, 에이전트 마스터리, 퀄리티 스트릭, 주간 기록
   - streaks.py (API): 250줄 — 4개 엔드포인트 (streaks, achievements, progress, gamification 대시보드)
   - test_streaks.py: 672줄 — 견고한 테스트
   - **총 1,418줄** — 이 정도 규모면 별도 아이디어 번호가 있어야 하는데, 백로그에 없음
   - 📌 **액션**: 이 기능을 백로그에 #237.5로 등록하거나, 기존 아이디어와 매핑 필요

3. **테스트 인프라 폭발적 성장**
   - 테스트 파일 **373개**, 총 **229,993줄**
   - Phase 44 시점 대비 약 5배 성장
   - 이 테스트 볼륨은 Enterprise-grade 프로젝트 수준

4. **Crawler 에이전트 활발**
   - 동작구 크롤러 개선 (사업비/공정률/조합원 추출, 입찰공고 파싱)
   - 서울시 크롤러 확장 (정비사업 통계, 토지경매 소스 2개 추가)
   - 237개 테스트 통과

### ⚠️ 방향성 조정 필요 (심각도 순)

#### 1. 🔴 Dev Codex 크론 연속 타임아웃 (20건 연속 에러)
- `consecutiveErrors: 20`, 매번 600초 타임아웃으로 실패
- **10분 × 20회 = 200분의 컴퓨팅 리소스 낭비** + 비용 손실
- 원인 추정: 테스트 스위트 229K줄 실행하면 600초 안에 끝나지 않음
- **즉시 조치 필요**: 
  - (a) timeout을 900초로 늘리거나
  - (b) `pytest -q --no-cov -x` (첫 실패 시 중단)로 전략 변경하거나
  - (c) 테스트 실행 없이 구현만 하도록 프롬프트 변경

#### 2. 🔴 BugFixer + Implementer + Planner WhatsApp 전달 실패
- `"Unsupported channel: whatsapp"` — 연속 에러 7~19건
- 작업 자체는 성공하지만 결과 알림이 안 감
- **즉시 조치**: delivery channel 설정 수정 필요 (whatsapp → webchat 또는 문제 해결)

#### 3. 🟡 Streak 기능 미커밋
- 1,418줄 작업이 unstaged/uncommitted 상태
- `git diff --stat`에 __init__.py만 나오고 나머지는 untracked
- 이 상태에서 다른 에이전트가 충돌 변경하면 작업 손실 가능
- **즉시 조치**: commit 필요

#### 4. 🟡 프론트엔드 12회 연속 권고 — 이제 해법 제시
- 더 이상 "프론트엔드 필요하다"만 반복하지 않겠음
- **구체적 해법**: Idea #237 (Demo Sandbox) + Idea #238 (CLI)
- React 풀 프론트엔드 대신, **Demo + CLI**로 사용자 접점 확보 → 이후 수요 기반으로 웹 UI 결정

---

## 💡 Phase 47 신규 아이디어 2개

> **카테고리**: 사용자 접점 (User Touchpoint) — 기능이 아닌 "전달 수단"

### Idea #237: "Zero-Config Demo Sandbox" 🎮
- **핵심**: Mock Google API로 3분 내 체험 가능한 데모 모드
- **기간**: 2일 / ~200줄
- **임팩트**: 온보딩 40분 → 3분. **외부 사용자 0 → N 전환의 열쇠**
- 상세: docs/ideas-backlog.md Phase 47 참조

### Idea #238: "Agent CLI" ⌨️
- **핵심**: pip install + 터미널에서 모든 AgentHQ 기능 접근
- **기간**: 2.5일 / MVP 150줄
- **임팩트**: 프론트엔드 없이 풀 기능 제공, 개발자 DX 극대화
- 상세: docs/ideas-backlog.md Phase 47 참조

---

## 🎯 즉시 실행 권고 우선순위 (Top 5)

| 순위 | 작업 | 이유 | 긴급도 |
|------|------|------|--------|
| 1 | **Dev Codex 크론 타임아웃 수정** | 200분 리소스 낭비 중 | 🔴 오늘 |
| 2 | **WhatsApp 전달 오류 수정** | 에이전트 3개 알림 불가 | 🔴 오늘 |
| 3 | **Streak 기능 커밋 + git push** | 1,418줄 미보호 코드 | 🟠 오늘 |
| 4 | **#237 Demo Sandbox** | 외부 사용자 확보의 전제조건 | 🟡 이번 주 |
| 5 | **#233 Test Coverage Sprint** | 229K줄 테스트의 실제 커버리지 확인 | 🟡 이번 주 |

---

## 🎯 설계자 에이전트 기술 검토 요청

### Idea #237 (Zero-Config Demo Sandbox)

1. **Mock 서비스 설계**: Google Docs/Sheets/Slides API를 Mock할 때, 현재 `google_service.py`의 인터페이스를 그대로 구현하는 게 맞는지? 아니면 별도 `demo_google_service.py`?
2. **환경 분리**: `DEMO_MODE=true` 환경 변수 하나로 전환? Docker Compose profile 분리?
3. **데이터 영속성**: demo 모드에서 만든 Task가 demo 종료 후 사라져도 되는지? (ephemeral SQLite vs persistent PostgreSQL)
4. **보안**: demo 모드에서 OAuth 스킵 시, JWT 토큰 어떻게 발급? 고정 demo 토큰?

### Idea #238 (Agent CLI)

1. **프레임워크 선택**: Click vs Typer vs argparse? Typer가 자동 완성 + help 생성에 유리하지만, 별도 패키지 의존성 추가됨.
2. **인증 흐름**: localhost:XXXX redirect로 OAuth code 받는 방식 — 포트 충돌 방지?
3. **실시간 Task 상태**: `agenthq status <id> --watch` 구현 시 polling vs WebSocket? CLI에서 WebSocket은 과한가?
4. **패키징**: `agenthq-cli` 별도 PyPI 패키지? 아니면 main 프로젝트의 extras (`pip install agenthq[cli]`)?

### Phase 46 미답변 사항 리마인드

- #235 (Preview → Chain): Preview LLM 프롬프트 확장 토큰 비용, 체이닝 실패 전파 정책
- #236 (Fallback Dashboard): 로그 저장 방식 (JSON 필드 vs 별도 모델), "Powered by X" 노출 리스크

---

## 📊 프로젝트 건강 지표

| 지표 | 값 | 추세 |
|------|-----|------|
| 총 아이디어 | 238개 | ↗ (모라토리엄 존중, +2개만) |
| 배포된 기능 | ~27개 | ↗ (+4건 72시간) |
| 실행 비율 | 11.3% | ↗ (6.5% → 11.3%) |
| 테스트 파일 | 373개 / 229K줄 | ↗↗ (폭발 성장) |
| 크론 에러 | Dev 20건, BugFixer 19건, Impl 18건 | 🔴 CRITICAL |
| git 상태 | remote 설정됨, push 미완 | 🟡 |
| 프론트엔드 | 미연결 (12회 권고) | → (해법 #237/#238 제시) |

---

## 🏆 기획자의 전략적 관점

> **Phase 1-46**: "어떤 기능을 만들까?" (아이디어 양산기)
> **Phase 47+**: "만든 기능을 어떻게 전달할까?" (실행 전환기)

238개 아이디어 중 실행된 건 27개. 이 비율을 높이는 건 **더 많이 만드는 것**이 아니라 **만든 것을 사용자에게 전달하는 것**입니다.

Demo Sandbox(#237)는 "전달의 전제조건"이고, CLI(#238)는 "전달의 수단"입니다. 이 두 가지가 없으면 나머지 236개 아이디어의 가치는 0입니다.

**다음 Phase부터 기획자 크론의 역할 전환을 제안합니다**:
- 아이디어 생성: 2개 → 0-1개
- 실행 추적: 30% → 50%
- 사용자 접점 전략: 0% → 30%
- 에이전트 인프라 건강 모니터링: 20% → 20%

---

작성: 기획자 크론 Phase 47 (2026-02-21 AM 07:20 UTC)
총 아이디어: **238개** (기존 236 + 신규 2: #237-238)
