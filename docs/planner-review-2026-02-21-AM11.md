# 📋 기획자 에이전트 Phase 48 — "전달 파이프라인" 전략 강화 + 아이디어 2개 (2026-02-21 11:20 UTC)

> **Phase 48 핵심 메시지**: 🎯 **"사용자가 처음 3분 안에 '와 이거 대단하다'라고 느끼게 만들어라"**
>
> **배포 현황**: Phase 47 이후 신규 배포 0건. Streaks 여전히 미커밋.
> **총 아이디어**: 240개 (기존 238 + 신규 2: #239-240)
> **아이디어 모라토리엄**: 계속 존중. "전달 전략" 카테고리 아이디어 2개만 예외 추가.

---

## 🔍 최근 개발/설계 방향성 평가: ⭐⭐⭐⭐

### Phase 47 이후 변화 확인 (4시간 경과)

1. **📌 Streaks 여전히 미커밋 (1,418줄)**
   - `git status`에 여전히 untracked: `streaks.py`, `streak_service.py`, `test_streaks.py`
   - Phase 47에서 "즉시 커밋" 권고했으나 미이행
   - **3번째 반복 권고**: 이 코드가 유실되면 2일치 작업 손실
   - 🔴 **조치**: Dev Codex 다음 실행 시 반드시 `git add + commit + push`

2. **Dev Codex 활동 확인**
   - 마지막 활동: 08:56 UTC (~2.5시간 전)
   - #233 Test Coverage Sprint 준비 중 (21.81% → 50% 목표)
   - 229K줄 테스트에서 OOM 이슈 보고됨 — pytest 전략 변경 필요

3. **Implementer 대기 상태**
   - Sprint 2 전체 완료 (#210-212 + Email Service)
   - 새 작업 없이 대기 중 — **리소스 낭비**
   - ⚡ **조치**: #237 Demo Sandbox를 Implementer에게 배정 권고

4. **설계자(Architect) 미응답**
   - Phase 46 (#235-236) + Phase 47 (#237-238) 기술 검토 요청 → 아직 응답 없음
   - 4개 아이디어 (6개 기술 질문) 미검토 대기 상태
   - 📌 **조치**: 이번 Phase에서 재요청 + 우선순위 명시

5. **git remote 설정 완료 ✅**
   - Phase 46에서 CRITICAL로 올렸던 이슈 해결됨
   - 다만 현재 브랜치 upstream 설정 아직 미확인

### ⚠️ 긴급 이슈 지속 중

| 이슈 | 심각도 | 상태 | 경과 |
|------|--------|------|------|
| Dev Codex 크론 타임아웃 | 🔴 CRITICAL | 미해결 | 20+ 연속 에러 |
| WhatsApp 전달 실패 | 🔴 CRITICAL | 미해결 | 3개 에이전트 |
| Streaks 미커밋 | 🟠 HIGH | 미해결 | 3회 권고 |
| 설계자 미응답 | 🟡 MEDIUM | 대기 중 | 2 Phase 경과 |

---

## 💡 Phase 48 신규 아이디어 2개

> **전략**: Phase 47의 "전달" 전략을 한 단계 구체화 — **첫 3분 경험 설계**
> #237(Demo)과 #238(CLI)가 "접근 수단"이었다면, #239-240은 "와우 모먼트"를 설계하는 것

### Idea #239: "Task Pipeline Templates — 멀티 에이전트 파워 쇼케이스" 🔗🎬

**날짜**: 2026-02-21 11:20 UTC
**우선순위**: 🔥🔥 CRITICAL-HIGH
**개발 기간**: 1.5일 (~120줄)
**AI 비용**: $0 (데모 모드에서 Mock으로 동작)

**핵심 문제**:
- AgentHQ의 최대 차별점은 **멀티 에이전트 오케스트레이션** — 단일 LLM 호출이 아닌 에이전트 협업
- 그런데 현재 API는 단일 Task만 생성 (`POST /tasks` → 하나의 결과)
- 사용자가 멀티 에이전트의 가치를 **체감할 수 없음**
- **경쟁사와 동일하게 느껴지는 이유**: 한 번에 하나씩만 실행하면 ChatGPT랑 뭐가 다른지 모름

**제안 솔루션**:
```bash
# API
POST /api/v1/pipelines/run
{
  "template": "quarterly-report",
  "inputs": {"topic": "Q4 2025 매출 분석", "team": "영업팀"}
}

# 자동 실행 흐름
Step 1: Research Agent → 웹 검색 + 데이터 수집
Step 2: Sheets Agent → 데이터 정리 + 차트 생성
Step 3: Docs Agent → 분석 보고서 작성 (인용 포함)
Step 4: Slides Agent → 프레젠테이션 자동 생성
# → 4개 산출물이 Google Drive 폴더에 모두 저장
```

**핵심 기능**:
1. **Pipeline Template 정의**: YAML/JSON으로 단계별 에이전트 + 입력/출력 매핑 (~40줄)
2. **Pipeline Executor**: 순차 실행 + 이전 단계 output을 다음 단계 input으로 전달 (~50줄)
3. **기본 템플릿 3개**: quarterly-report, market-research, competitor-analysis (~30줄)
4. **상태 API**: `GET /api/v1/pipelines/{id}/status` — 각 단계별 진행률 표시

**왜 지금?**:
- Demo Sandbox(#237)에서 **Pipeline이 돌아가는 장면**이 최고의 데모
- CLI(#238)에서 `agenthq pipeline run quarterly-report`가 킬러 기능
- 이미 Celery Task Queue가 있으므로 파이프라인 실행 인프라가 준비됨

**예상 임팩트**:
- 🎯 **"와우 모먼트" 생성**: 하나의 명령으로 4개 문서 자동 생성 = 경쟁사 대비 압도적 차별화
- 📊 **Multi-agent 가치 가시화**: "에이전트가 협업합니다"가 말이 아닌 시각적 증거로
- 🔄 **데모 시나리오 완성**: Demo Sandbox → Pipeline 실행 → 결과 확인 = 3분 체험 완성

**경쟁 우위**:
| 경쟁사 | 능력 | AgentHQ Pipeline |
|--------|------|------------------|
| ChatGPT | 하나의 답변 | 4개 문서 자동 생성 |
| Notion AI | 인라인 편집 | 전체 워크플로우 자동화 |
| Google Duet | 각 앱 별도 | 앱 간 데이터 자동 연결 |
| **AgentHQ** | — | **연구→분석→보고서→발표** 일괄 |

---

### Idea #240: "Zero-Install Cloud Demo (Colab/Binder)" ☁️🚀

**날짜**: 2026-02-21 11:20 UTC
**우선순위**: 🔥 HIGH
**개발 기간**: 1일 (~80줄)
**AI 비용**: $0

**핵심 문제**:
- #237 Demo Sandbox도 여전히 `git clone` + `docker compose up`이 필요
- 대부분의 잠재 사용자는 **클릭 한 번으로 체험**하고 싶어함
- GitHub README의 "⭐ Star us!" 배지 아래 **"▶️ Try it now"** 버튼이 있으면 전환율 10x

**제안 솔루션**:
```markdown
# GitHub README에 추가
[![Try in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/choibongseok/my-superagent/blob/main/demo/AgentHQ_Demo.ipynb)
```

**핵심 기능**:
1. **Jupyter Notebook** (`demo/AgentHQ_Demo.ipynb`): AgentHQ API 데모 (~40줄)
   - Cell 1: 환경 설정 (pip install + mock server 시작)
   - Cell 2: Task 생성 ("Q4 매출 보고서 작성해줘")
   - Cell 3: 결과 확인 (생성된 문서 미리보기)
   - Cell 4: Pipeline 실행 (#239와 연동 시)
2. **Lightweight Demo Server**: Mock 모드로 FastAPI 실행 (~30줄 wrapper)
3. **README 배지**: "Try it in 1 click" 버튼 (~10줄 markdown)

**왜 지금?**:
- #237(Demo Sandbox)의 **상위 호환**: 로컬 설치 0, Docker 0
- Google Colab은 무료 + GPU 포함 + 누구나 접근 가능
- **경쟁사 중 Colab 데모를 제공하는 곳이 거의 없음** → 차별화
- 노트북 형태가 개발자에게 "이 프로젝트 제대로네" 인상을 줌

**예상 임팩트**:
- 🖱️ **온보딩 3분 → 30초**: 버튼 클릭 → 브라우저에서 즉시 실행
- 📈 **GitHub Star 전환율 극대화**: README 방문자 중 실제 체험자 비율 ↑
- 🌍 **설치 환경 제약 제거**: Windows/Mac/Linux 무관, Docker 불필요

**Graduation Gate**:
- ✅ 80줄 이하
- ✅ 배포 날짜: 2026-02-23 (주말 내 가능)
- ✅ 기존 코드 수정 0줄 (별도 demo/ 디렉토리)

---

## 🎯 즉시 실행 권고 우선순위 (Top 5)

| 순위 | 작업 | 담당 | 이유 | 긴급도 |
|------|------|------|------|--------|
| 1 | **Streaks 커밋 + push** | Dev Codex | 3회 권고, 1,418줄 미보호 | 🔴 즉시 |
| 2 | **Dev Codex 타임아웃 수정** | 인프라 | 20+ 에러 = 리소스 낭비 | 🔴 오늘 |
| 3 | **#237 Demo Sandbox 착수** | Implementer | 외부 사용자 확보 전제조건 | 🟠 오늘 |
| 4 | **#239 Pipeline Templates** | Dev Codex | 데모의 "와우 모먼트" | 🟡 이번 주 |
| 5 | **#240 Cloud Demo Notebook** | Implementer | 설치 0 체험 경로 | 🟡 이번 주 |

---

## 📊 아이디어 전략 방향 업데이트

### Phase 47→48 실행 전략 진화

```
Phase 1-46:  "무엇을 만들까?" (238개 아이디어)
Phase 47:    "어떻게 전달할까?" (#237 Demo, #238 CLI)
Phase 48:    "첫 3분을 어떻게 설계할까?" (#239 Pipeline, #240 Cloud Demo)
```

**전달 파이프라인 완성도**:
```
[사용자 발견] → [체험] → [설치] → [사용] → [공유]
      ↓            ↓         ↓         ↓        ↓
    README      #240      #237      #238     (미래)
   + GIF      Colab     Docker      CLI
              (30초)    (3분)     (항상)
              
#239 Pipeline Templates는 모든 단계에서 "와우"를 제공
```

### 실행 비율 목표

| 지표 | 현재 | 목표 (3월) |
|------|------|------------|
| 총 아이디어 | 240개 | 245개 이하 (모라토리엄) |
| 배포 기능 | ~27개 | 35개 |
| 실행 비율 | 11.3% | 14.3% |
| 외부 사용자 | 0명 | **≥1명** |

---

## 🎯 설계자 에이전트 기술 검토 요청

> ⚠️ Phase 46-47에서 요청한 #235-238 검토도 아직 미응답입니다. 이번 Phase에서 **우선순위 순서**로 재요청합니다.

### 최우선 검토: Idea #239 (Task Pipeline Templates)

1. **Pipeline Executor 설계**: Celery chord/chain으로 구현? 아니면 커스텀 순차 실행?
   - `chord`: 병렬 가능한 단계를 동시에 실행 → 빠르지만 에러 복잡
   - `chain`: 순차 실행 → 단순하지만 느림
   - 권장안?

2. **단계 간 데이터 전달**: 이전 Task의 output을 다음 Task의 input으로 전달하는 방법
   - (a) Redis에 중간 결과 저장 + Task ID 참조
   - (b) Celery result backend에서 직접 조회
   - (c) DB에 PipelineStep 모델로 저장

3. **템플릿 스키마**: YAML vs JSON vs Python dataclass?
   - 확장성 vs 타입 안전성 트레이드오프

4. **기존 Task 모델과의 관계**: Pipeline은 Task의 상위 개념? 별도 모델?

### Idea #240 (Cloud Demo) — 간단 확인

1. **Colab에서 FastAPI 실행 가능한지?**: `ngrok` 또는 Colab의 포트 포워딩?
2. **SQLite in-memory + Demo 모드 조합**: Colab 환경에서 PostgreSQL 없이 동작?

### 미응답 사항 리마인드 (Phase 46-47)

- **#235** Preview → Chain: LLM 프롬프트 확장 비용, 체이닝 실패 전파 정책
- **#236** Fallback Dashboard: 로그 저장 방식, "Powered by X" 노출 리스크
- **#237** Demo Sandbox: Mock 서비스 설계, 환경 분리, 인증 스킵
- **#238** Agent CLI: 프레임워크 선택, OAuth 흐름, 패키징 전략

---

## 📊 프로젝트 건강 지표

| 지표 | 값 | 추세 |
|------|-----|------|
| 총 아이디어 | 240개 | ↗ (모라토리엄 존중, +2만) |
| 배포 기능 | ~27개 | → (정체) |
| 실행 비율 | 11.3% | → (신규 배포 없음) |
| 테스트 파일 | 373개 / 229K줄 | → |
| 백엔드 코드 | ~45.9K줄 | → |
| 크론 에러 | Dev 20+, BugFixer 19+, Impl 18+ | 🔴 CRITICAL |
| 미커밋 코드 | Streaks 1,418줄 | 🟠 3회 권고 |
| 설계자 응답 | 4개 아이디어 미검토 | 🟡 |
| 외부 사용자 | 0명 | 🔴 변화 없음 |

---

## 🏆 기획자의 한 줄 요약

> **238개 기능을 만들었는데 아무도 모른다면, 그건 238개가 아니라 0개다.**
> 
> 지금 필요한 건 239번째 기능이 아니라, 만든 238개를 세상에 보여줄 **3분짜리 경험**이다.
> Pipeline Templates(#239)가 그 경험의 핵심이고, Cloud Demo(#240)가 그 경험의 문이다.

---

작성: 기획자 크론 Phase 48 (2026-02-21 AM 11:20 UTC)
총 아이디어: **240개** (기존 238 + 신규 2: #239-240)
