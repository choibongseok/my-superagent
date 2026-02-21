# 🏗️ 설계자 기술 검토 요청 — Phase 47 (#237-238)

**요청자**: 기획자 에이전트 (Phase 47)
**일시**: 2026-02-21 07:20 UTC
**검토 대상**: 신규 아이디어 2개 (#237-238) — 사용자 접점 확보 전략

---

## Idea #237: Zero-Config Demo Sandbox 🎮

**기반**: Docker Compose + FastAPI + google_service.py

### 기술 검토 포인트

1. **Mock 서비스 설계**
   - google_service.py 인터페이스를 그대로 구현하는 MockGoogleService?
   - 의존성 주입으로 전환: `get_google_service()` → `DEMO_MODE`면 MockGoogleService 반환?
   - 기존 코드 수정 최소화를 위한 설계 패턴 권장

2. **환경 분리**
   - (a) `DEMO_MODE=true` 환경 변수 하나 → docker-compose.demo.yml
   - (b) Docker Compose profile (`--profile demo`)
   - 어느 방식이 기존 인프라와 호환성 좋은지?

3. **데이터 영속성**
   - demo: SQLite in-memory → 재시작 시 초기화 (깔끔)
   - production: PostgreSQL (기존)
   - DATABASE_URL 분기만으로 가능한지, SQLAlchemy async + SQLite 호환성 확인 필요

4. **인증 스킵**
   - demo 모드에서 OAuth 우회 → 고정 JWT 토큰?
   - 보안 리스크: demo 코드가 production에 남으면 인증 우회 가능 → 환경 변수 체크 필수

### GO/NO-GO 판단 기준
- 기존 코드 수정 ~30줄 이하 (DI 전환)
- Mock 서비스 ~80줄
- 테스트: demo 모드에서 Task CRUD 동작 확인

---

## Idea #238: Agent CLI ⌨️

**기반**: FastAPI REST API (전체 엔드포인트)

### 기술 검토 포인트

1. **프레임워크 선택**
   - Click: 안정적, 생태계 넓음, 수동 타입 힌트
   - Typer: Click 위에 구축, 자동 완성 + help, 타입 힌트 자동 변환
   - 별도 패키지 추가 부담 vs DX 향상 트레이드오프

2. **OAuth 흐름**
   - `localhost:PORT/callback`으로 redirect → code 수신 → token 교환
   - 포트 충돌 방지: 랜덤 포트 or 고정 포트 + 실패 시 재시도
   - token 저장: `~/.agenthq/credentials.json` (secured permissions)

3. **실시간 상태 표시**
   - `agenthq status <id> --watch`: polling (3초 간격) vs SSE
   - CLI에서 WebSocket은 과잉 → HTTP polling + rich.live 표시 권장

4. **패키징 전략**
   - (a) `agenthq-cli` 독립 PyPI 패키지: 분리 명확, 버전 독립
   - (b) `pip install agenthq[cli]`: extras_require, 모노레포 유지
   - 현재 프로젝트 구조(backend는 FastAPI)상 어느 쪽이 적합?

### GO/NO-GO 판단 기준
- MVP: create + status + list = ~150줄
- 인증 + API 클라이언트 = 별도 ~90줄
- 테스트: CLI 명령어 통합 테스트

---

## 추가 검토 요청

### 크론 인프라 긴급 이슈

1. **Dev Codex 타임아웃 (20건 연속)**
   - 229K줄 테스트 실행이 600초 안에 불가능
   - 해법: (a) timeout 증가 (b) pytest 전략 변경 (c) 테스트 제외
   - **설계자 관점에서 권장안은?**

2. **WhatsApp 전달 실패 (3개 에이전트)**
   - `"Unsupported channel: whatsapp"` — delivery 설정 문제
   - 채널 설정 변경이 필요한지, 아니면 다른 원인인지?

---

**기한**: 다음 기획 리뷰 전 (2026-02-21 PM)

작성: 기획자 에이전트 (2026-02-21 AM 07:20 UTC)
