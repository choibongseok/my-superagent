# 📋 기획자 에이전트 Phase 50 — "실행 재점화" + 아이디어 3개 (#243-245) (2026-02-22 01:20 UTC)

> **Phase 50 핵심 메시지**: 🎯 **"242개 아이디어, 0명 사용자. 이제 문제는 아이디어가 아니라 실행 인프라다."**
>
> **배포 현황**: Phase 49 이후 신규 코드 커밋 0건 (10시간 경과)
> **총 아이디어**: 245개 (기존 242 + 신규 3: #243-245)
> **아이디어 모라토리엄**: ~18시간 남음 (2026-02-22 PM 7:20 해제). 실행 인프라 + 차별화 핵심 기능만 예외.

---

## 🔍 최근 개발/설계 방향성 평가: ⭐⭐ (위기)

### Phase 49 이후 변화 확인 (10시간 경과, 15:25 → 01:20 UTC)

1. **🔴 코드 커밋 0건 — 10시간 정체**
   - 마지막 코드 커밋(`0c8c3ed` fix tests): 2026-02-21 이전
   - 이후 커밋은 전부 plan/docs 문서 — 실제 기능 개발 없음
   - Phase 45의 실행력 ⭐⭐⭐⭐⭐에서 급격한 하락

2. **🔴 미커밋 코드 5회 연속 경고 — 이제 EMERGENCY**
   - `git status`에 여전히 untracked:
     - `streaks.py`, `streak_service.py`, `test_streaks.py`
     - `chains.py`, `chain_service.py`, `test_chains_api.py`
     - `task_chain.py`, `chain.py`
   - **추정 2,500줄+ 미보호 코드**
   - Phase 45부터 5회 연속 권고. 더 이상 "권고"가 아니다.
   - 🔴 **이건 기획자가 해결할 문제가 아님 — 개발자가 즉시 실행해야 함**

3. **🔴 설계자(Architect) 여전히 응답 불가 — 4 Phase 연속**
   - Phase 46-49에서 총 8건 검토 요청 → **전부 미응답**
   - 원인: 설계자 세션이 BotManager 워크스페이스를 바라보는 라우팅 오류
   - **결과**: 기획자가 아무리 좋은 아이디어를 내도 기술 검증 없이 개발자에게 전달됨
   - 이것은 **프로세스의 구조적 결함** — 기획→설계→개발 파이프라인이 끊어진 상태

4. **Dev Codex 크론 타임아웃 지속 (20회+)**
   - 개발 에이전트 자체가 제대로 동작하지 않는 상태
   - 인프라 이슈가 모든 것을 병목시킴

5. **Factory 프로젝트로 리소스 분산**
   - Factory Dev가 활발히 활동 (About 페이지, SpeedDial FAB 등)
   - Redeviq 크롤러 30차 개선도 진행 중
   - AgentHQ 개발 리소스가 다른 프로젝트에 투입되고 있음

---

## ⚠️ 위기 진단: 왜 242개 아이디어가 있는데 0명이 쓰는가?

### 근본 원인 분석

```
[기획] ──→ [설계] ──→ [개발] ──→ [배포] ──→ [사용자]
  ✅ 242개    ❌ 라우팅깨짐    ⚠️ 정체    ❌ 없음     ❌ 0명
  
문제점:
1. 기획만 과잉 — 2시간마다 아이디어 2-3개 생산 (하루 30개+)
2. 설계 파이프라인 끊김 — 4 Phase째 기술 검증 불가
3. 개발 인프라 고장 — 크론 타임아웃, 세션 라우팅 오류
4. 배포 수단 없음 — docker-compose만 존재, 클릭 한 번으로 시도할 방법 없음
5. 미커밋 코드 2,500줄 — 물리적 코드 유실 위험
```

### 기획자의 자기 반성

솔직히, **기획자(나)도 문제의 일부다**. 242개 아이디어는 "생산성"이 아니라 "noise"다.
실행 비율 11.2%는 아이디어의 89%가 낭비되었다는 뜻이다.

**다음 Phase부터의 전략 전환**:
- 신규 아이디어: Phase당 최대 1개 (지금까지 2-3개/Phase)
- 회고/피드백에 80% 시간 투자
- 기존 미구현 아이디어 중 상위 5개만 집중 추적
- **모라토리엄 해제 후에도 자기 제한 유지**

---

## 💡 Phase 50 신규 아이디어 3개 (실행 인프라 + 핵심 차별화에 한정)

> **전략**: 242개 중 대부분은 "있으면 좋은 기능". 이번 3개는 **"없으면 사용자가 안 오거나 떠나는 기능"**만.
> 모라토리엄 중이지만, 이 3가지는 제품 생존에 직결됨.

### Idea #243: "Agent Memory Timeline — AI가 나를 기억한다는 증거" 🧠📅

**날짜**: 2026-02-22 01:20 UTC
**우선순위**: 🔥🔥 CRITICAL-HIGH
**개발 기간**: 1일 (~90줄)
**AI 비용**: $0

**핵심 문제**:
- 현재 Memory 시스템(ConversationMemory + VectorMemory)은 내부적으로 잘 동작
- **하지만 사용자가 이걸 체감할 수 없음** — "AI가 정말 나를 기억해?" 확인 불가
- ChatGPT도 "memory" 기능이 있지만, 사용자가 관리할 수 있는 UI를 제공
- AgentHQ는 "기억합니다"라고 말하지만 증거를 보여주지 않음

**제안 솔루션**:
```
[Memory Timeline 페이지]
┌────────────────────────────────────────────────────────┐
│ 🧠 에이전트가 기억하는 것들                              │
│                                                        │
│ 📅 2026-02-22                                          │
│   🔹 "Q4 매출 데이터는 Sheets에 정리" (Research Agent)  │
│   🔹 "선호 차트 스타일: 막대그래프" (Sheets Agent)       │
│                                                        │
│ 📅 2026-02-21                                          │
│   🔹 "경쟁사 분석 시 A사, B사 중점 비교" (Research)      │
│   🔹 "보고서 형식: 한국어, 존댓말" (Docs Agent)          │
│                                                        │
│ [🗑️ 삭제] [✏️ 편집] [➕ 직접 추가]                       │
└────────────────────────────────────────────────────────┘
```

**핵심 기능**:
1. **Memory Query API** (~30줄): `GET /api/v1/memory/timeline` — 기존 MemoryManager에서 사용자별 기억 추출
   - VectorMemory의 stored embeddings를 시간순으로 조회
   - ConversationMemory의 key facts 추출
2. **Memory CRUD** (~30줄): 사용자가 기억을 직접 추가/수정/삭제
   - "항상 한국어로 보고서 작성해줘" → 수동 메모리 등록
   - 잘못된 기억 삭제 가능
3. **Timeline UI** (~30줄): 시간순 카드 목록

**왜 이게 중요한가**:
- **리텐션**: "이 AI는 나를 알아" → 다른 AI로 전환 시 "처음부터 다시 가르쳐야 해" = 전환 비용
- **신뢰**: 기억의 투명성 = 사용자가 AI를 더 신뢰
- **차별화**: ChatGPT는 단순 키워드 메모리, AgentHQ는 에이전트별 전문 기억

**경쟁 벤치마크**:
| 도구 | 메모리 시스템 | 사용자 가시성 | 편집 가능 |
|------|-------------|--------------|-----------|
| ChatGPT | ✅ Memory | ✅ 설정에서 확인 | ✅ 삭제 가능 |
| Claude | ❌ | ❌ | ❌ |
| AgentHQ | ✅ 존재 | ❌ 안 보임 | ❌ |
| **AgentHQ + #243** | ✅ | ✅ 타임라인 | ✅ CRUD |

**Graduation Gate**: ✅ 90줄 이하, 1일, 기존 MemoryManager 활용

**예상 임팩트**:
- 🧲 **전환 비용 생성**: 사용자의 축적된 메모리 = 떠나기 아까운 자산
- 🤝 **신뢰 구축**: "이 AI는 투명하다"
- 📈 **리텐션 +30% 예상**: 개인화된 AI는 범용 AI보다 이탈률이 낮음

---

### Idea #244: "Scheduled Auto-Reports — 매주 알아서 만들어주는 보고서" ⏰📊

**날짜**: 2026-02-22 01:20 UTC
**우선순위**: 🔥🔥🔥 CRITICAL (사용자 고착화 핵심)
**개발 기간**: 1-2일 (~120줄)
**AI 비용**: 실행 시 LLM 비용 (사용자당)

**핵심 문제**:
- 현재 AgentHQ는 **매번 사용자가 직접 요청**해야 작동
- "매주 월요일 주간 보고서" → 매주 직접 명령해야 함
- 이건 **자동화 플랫폼**인데 정작 반복 작업이 자동화 안 됨
- **가장 강력한 고착(lock-in) 장치**: 한 번 설정하면 매주 알아서 보고서가 나옴 → 해지 시 보고서 작성을 다시 직접 해야 함

**제안 솔루션**:
```python
# Schedule 모델 추가 (~20줄)
class TaskSchedule(Base):
    user_id: int
    task_template_id: int
    cron_expression: str  # "0 9 * * 1" = 매주 월 9시
    last_run: datetime
    next_run: datetime
    is_active: bool

# Celery Beat 스케줄러 연동 (~50줄)
@celery.task
def execute_scheduled_task(schedule_id):
    schedule = get_schedule(schedule_id)
    create_and_execute_task(schedule.task_template_id, schedule.user_id)

# API 엔드포인트 (~50줄)
POST /api/v1/schedules          # 스케줄 생성
GET  /api/v1/schedules          # 내 스케줄 목록
PUT  /api/v1/schedules/{id}     # 수정
DELETE /api/v1/schedules/{id}   # 삭제
```

**사용 시나리오**:
```
사용자: "매주 월요일 아침 9시에 주간 실적 보고서 만들어줘"
AgentHQ: ✅ 스케줄 등록! 다음 실행: 2026-02-23 (월) 09:00

→ 매주 월요일 9시 자동 실행
→ Research Agent: 최신 데이터 수집
→ Sheets Agent: 데이터 정리 + 차트 생성
→ Docs Agent: 보고서 작성
→ 사용자 이메일로 완성 보고서 링크 전송
```

**왜 이게 "킬러 기능"인가**:
- **Zapier/Make.com의 핵심 가치가 "자동 반복"** — AgentHQ는 이걸 AI로 하는 것
- **고착화**: 10개 보고서가 매주 자동 생성 → 해지 = 10개를 직접 다시 만들어야 함
- **MAU 보장**: 자동 실행 = 사용자가 안 들어와도 가치를 계속 받음
- **B2B 핵심**: 기업은 "반복 업무 자동화"에 비용을 지불

**기술 기반**:
- Celery Beat + Redis 이미 구성됨 (`docker-compose.yml`)
- TaskTemplate 시스템 이미 존재 (Phase 1)
- Email Service 이미 구현됨 (389줄)

**경쟁 벤치마크**:
| 도구 | 반복 실행 | 자동화 수준 |
|------|----------|------------|
| ChatGPT | ❌ | 매번 수동 |
| Notion AI | ❌ | 매번 수동 |
| Zapier | ✅ 트리거 | 규칙 기반만 |
| **AgentHQ + #244** | ✅ 스케줄 | AI 에이전트가 자동 생산 |

**Graduation Gate**: ✅ 120줄 이하, 1-2일, Celery Beat 활용

**예상 임팩트**:
- 🔒 **최고의 고착화 장치**: "자동 보고서 10개 설정함" → 절대 해지 안 함
- 📧 **자동 리텐션**: 매주 이메일로 가치 전달 = 사용자가 잊어도 AgentHQ는 작동
- 💰 **B2B 매출 직결**: "매주 2시간 절약" = 월 X만원 가치

---

### Idea #245: "Instant Cloud Preview — 코드 한 줄 없이 미리보기" ☁️👀

**날짜**: 2026-02-22 01:20 UTC
**우선순위**: 🔥 HIGH
**개발 기간**: 0.5일 (~60줄)
**AI 비용**: $0

**핵심 문제**:
- README에서 프로젝트를 발견한 개발자/사용자가 시도하려면:
  1. 클론 → 2. Docker 설치 → 3. .env 설정 → 4. API 키 발급 → 5. docker-compose up
  - **최소 20분, 최대 1시간** → 대부분의 잠재 사용자가 이 단계에서 이탈
- #240(Cloud Demo)은 Colab/Codespace 기반이었지만, 아직 미구현
- **가장 빠른 해결**: GitHub README에 Gitpod/Codespace 버튼 1개 추가

**제안 솔루션**:
```markdown
<!-- README.md에 추가할 1줄 -->
[![Open in GitHub Codespaces](https://img.shields.io/badge/Open_in-Codespaces-blue?logo=github)](https://codespaces.new/choibongseok/my-superagent)

<!-- .devcontainer/devcontainer.json (~30줄) -->
{
  "name": "AgentHQ Dev",
  "dockerComposeFile": "../docker-compose.yml",
  "service": "backend",
  "forwardPorts": [8000, 5555],
  "postCreateCommand": "pip install -r requirements.txt && alembic upgrade head",
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "humao.rest-client"]
    }
  }
}

<!-- API 데모용 .env.demo (~30줄) -->
# OpenAI API 키 없이 동작하는 Mock 모드
DEMO_MODE=true
LLM_PROVIDER=mock  # 실제 API 호출 없이 샘플 응답 반환
```

**핵심 기능**:
1. **devcontainer.json** (~30줄): GitHub Codespaces 1-click 시작
2. **Demo Mock Mode** (~30줄): API 키 없이도 동작하는 Mock LLM provider
   - 실제 Google Sheets/Docs 생성 대신 샘플 JSON 응답
   - Swagger UI에서 바로 API 테스트 가능
   - "이런 식으로 동작합니다" 체험

**왜 이게 중요한가**:
```
현재 사용자 획득 퍼널:
README 발견(100%) → 클론(10%) → 환경 설정(3%) → 실행(1%) → 사용(0.5%)

#245 적용 후:
README 발견(100%) → Codespace 클릭(40%) → 즉시 체험(35%) → 사용(10%)
```

**기술 기반**:
- docker-compose.yml 이미 존재
- FastAPI Swagger UI 이미 동작
- GitHub Codespaces는 무료 제공 (월 120시간)

**Graduation Gate**: ✅ 60줄 이하, 0.5일

**예상 임팩트**:
- 🚀 **사용자 획득 퍼널 10x 개선**: 20분 설정 → 30초 클릭
- 📊 **첫 사용자 확보 가능**: 설정 장벽 제거 = 사용 가능
- 🎯 **#237 Demo Sandbox의 초경량 버전**: 실행 가능성 극대화

---

## 📊 전체 아이디어 실행 현황 업데이트

| 지표 | 값 | 추세 | 비고 |
|------|-----|------|------|
| 총 아이디어 | 245개 | ↗ (+3) | 모라토리엄 중 최소한으로 제한 |
| 배포 기능 | ~27개 | → (정체) | 10시간 새 커밋 0건 |
| 실행 비율 | 11.0% | ↘ | 분모↑, 분자→ |
| 테스트 | 2,166개+ | → | |
| 미커밋 코드 | ~2,500줄 | 🔴 5회 경고 | chains + streaks |
| 설계자 응답 | 0/8건 (4 Phase) | 🔴 라우팅 오류 | |
| 외부 사용자 | 0명 | 🔴 | |

---

## 🎯 즉시 실행 권고 우선순위

| 순위 | 작업 | 담당 | 긴급도 | 비고 |
|------|------|------|--------|------|
| 1 | **미커밋 코드 즉시 커밋** | Dev/Implementer | 🔴 NOW | `git add . && git commit` |
| 2 | **설계자 크론 세션 수정** | 인프라/사용자 | 🔴 NOW | 세션이 BotManager를 바라보는 중 |
| 3 | **Dev Codex 크론 타임아웃 수정** | 인프라 | 🔴 오늘 | 20회+ 연속 실패 |
| 4 | **#245 Instant Cloud Preview** | Dev | 🟠 오늘 | 사용자 획득의 최소 조건 |
| 5 | **#244 Scheduled Auto-Reports** | Dev | 🟠 이번 주 | 킬러 고착화 기능 |
| 6 | **#243 Memory Timeline** | Dev | 🟡 이번 주 | 리텐션 강화 |

---

## 🏆 기획자의 한 줄 요약

> **242개 아이디어를 만든 기획자로서 인정한다: 문제는 아이디어가 아니라 실행 인프라다.**
> 설계자 세션이 4 Phase째 죽어있고, 2,500줄 코드가 커밋 안 되어있고, 사용자 유입 경로가 없다.
> 이번 Phase부터 기획자도 자기 제한: Phase당 최대 1개 아이디어. 나머지 시간은 실행 추적에 투자.

---

작성: 기획자 크론 Phase 50 (2026-02-22 AM 1:20 UTC)
총 아이디어: **245개** (기존 242 + 신규 3: #243-245)
