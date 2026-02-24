# 💡 AgentHQ 아이디어 검토 및 방향성 피드백

> **검토 날짜**: 2026-02-24 10:14 UTC  
> **검토자**: Architect Agent (Architect Review Cron)  
> **목적**: 최신 커밋 반영 검토 + Idea Eval 기록

---

## 📋 최근 개발 작업 검토 (2026-02-22 ~ 2026-02-24)

### ✅ 최근 개발 성과

**개발 속도**: 매우 빠름 (48시간 동안 6,224줄 추가, 350줄 삭제)

**주요 신규 기능**:
1. **Error Recovery Service** (`error_recovery.py`) ⭐⭐⭐⭐⭐
   - 12개 에러 카테고리 분류
   - 자동 복구 제안 생성
   - 81개 테스트 커버

2. **Demo Mode** (`mock_llm.py`) ⭐⭐⭐⭐⭐
   - API 키 없이 동작하는 Mock LLM
   - 신규 사용자 진입 장벽 대폭 하락
   - 226개 테스트

3. **Recovery Deck API** ⭐⭐⭐⭐⭐
   - 실패 작업의 체계적 복구 경로 제공
   - 228개 테스트

4. **Reliability Gate API** ⭐⭐⭐⭐⭐
   - 실행 전 신뢰성 진단
   - 180개 테스트

5. **Smart Exit Hints API** ⭐⭐⭐⭐⭐
   - 작업 완료 후 다음 액션 제안
   - 211개 테스트

6. **Share Link 만료 기능** ⭐⭐⭐⭐
   - 보안 강화

7. **Memory Timeline API** ⭐⭐⭐⭐
   - AI 기억의 시각화

8. **Nudge Email 개선** ⭐⭐⭐⭐
   - 주간 전송 상한 체크

**테스트 상황**: 매우 양호 (새 기능마다 종합 테스트 보유)

---

## 🏗️ 아키텍처 현황 분석

### ✅ 강점

1. **완성도 높은 에러 처리 시스템**
   - `error_recovery.py`: 12개 카테고리 + 자동 복구 제안
   - `reliability-gate`: 실행 전 사전 진단
   - `recovery-deck`: 실패 후 복구 경로

2. **견고한 테스트 커버리지**
   - 신규 기능마다 100+ 테스트
   - 통합 테스트 + 단위 테스트 병행

3. **사용자 경험 개선 인프라**
   - `smart-exit-hints`: 완료 후 다음 액션
   - `task_preview.py`: 실행 전 미리보기
   - `onboarding_service.py`: 신규 사용자 온보딩

4. **Demo Mode로 진입 장벽 해소**
   - API 키 없이 즉시 체험 가능

### ⚠️ 구조적 개선 포인트

1. **Chain 실행 오케스트레이션 미완성 (P0)**
   - 현재 상태: `chain_service._execute_current_step()`이 Task 생성까지만 수행
   - 문제: Celery 큐 투입 및 완료 후 다음 단계 진행 로직 누락
   - 권장: `celery_app.update_task_status`에 체인 진행 훅 추가

2. **모델 마이그레이션 가시성 (P1)**
   - `models/__init__.py`와 `alembic/env.py`에 신규 모델 미등록
   - `TaskChain`, `ScheduledTask` 등이 자동 마이그레이션에서 누락될 수 있음

3. **사용자 활동 추적 일관성 (P1)**
   - `last_task_created_at` 업데이트가 일부 경로에서 누락
   - `send_nudge_emails`의 비활성 사용자 판단에 영향

---

## 🔍 신규 아이디어 기술 검토 (#276~#281)

### 💡 Idea #276: Reliability Landing Page — 실패 복구 랜딩

**날짜**: 2026-02-24 05:22 UTC

#### 기술적 타당성: 🟢 즉시 구현 가능 ⭐⭐⭐⭐⭐

**기존 인프라 활용**:
- ✅ `error_recovery.py` (에러 분류 + 복구 제안)
- ✅ `recovery-deck` API (실패 복구 경로)
- ✅ `reliability-gate` API (실행 전 진단)
- ✅ `chain_service.py` (체인 진행 상태)

**구현 방법**:
```python
# GET /api/v1/tasks/{task_id}/recovery-landing
# 응답 구조:
{
  "error_category": "PERMISSION_DENIED",
  "friendly_message": "권한이 부족합니다",
  "recovery_actions": [
    {"type": "retry", "label": "재시도"},
    {"type": "reauth", "label": "권한 재연동"},
    {"type": "simplify", "label": "프롬프트 단순화"}
  ],
  "chain_progress": {
    "completed": 2,
    "total": 5,
    "next_step": "Slides 생성"
  }
}
```

**개발 공수**: 1~1.5일 (기존 API 조합 + UI 페이지)  
**난이도**: ⭐⭐☆☆☆ (쉬움)  
**우선순위**: 🔥 HIGH  
**판정**: ✅ GO — 기존 인프라로 80% 완성 가능

---

### 💡 Idea #277: Chain Progress Dock — 체인 진행 도크

**날짜**: 2026-02-24 05:22 UTC

#### 기술적 타당성: 🟡 조건부 가능 ⭐⭐⭐⭐☆

**기존 인프라 활용**:
- ✅ `chain_service.py` (체인 상태 관리)
- ⚠️ WebSocket 실시간 업데이트 필요 (현재 polling 방식)
- ✅ Task 실행 로그 존재

**필요한 추가 구현**:
1. WebSocket 이벤트: `chain.step.started`, `chain.step.completed`, `chain.step.failed`
2. 체인 단계별 예상 시간 계산 (과거 실행 통계 기반)
3. UI: 타임라인 도크 컴포넌트

**구현 방법**:
```python
# GET /api/v1/chains/{chain_id}/progress
{
  "steps": [
    {
      "step_id": "step1",
      "status": "completed",
      "elapsed_ms": 12500,
      "logs_snippet": "문서 생성 완료"
    },
    {
      "step_id": "step2",
      "status": "running",
      "estimated_remaining_ms": 8000,
      "logs_snippet": "시트 데이터 수집 중..."
    }
  ]
}
```

**개발 공수**: 2~3일 (WebSocket 추가 + UI)  
**난이도**: ⭐⭐⭐☆☆ (중간)  
**우선순위**: 🔥 HIGH  
**판정**: ✅ GO (조건부) — WebSocket 우선 구축 필요

---

### 💡 Idea #278: Smart Follow-Through Hub — 후속 작업 허브

**날짜**: 2026-02-24 05:22 UTC

#### 기술적 타당성: 🟢 즉시 구현 가능 ⭐⭐⭐⭐⭐

**기존 인프라 활용**:
- ✅ `smart-exit-hints` API (완료 후 액션 제안)
- ✅ `share.py` (공유 기능)
- ✅ `schedules.py` (일정 등록)
- ✅ `templates.py` (템플릿 재사용)
- ✅ `memory.py` (작업 이력 저장)

**구현 방법**:
```python
# GET /api/v1/tasks/{task_id}/follow-through
{
  "task_id": "uuid",
  "completed_at": "2026-02-24T10:00:00Z",
  "suggested_actions": [
    {
      "type": "share",
      "priority": 1,
      "label": "팀에 공유",
      "action_url": "/api/v1/share/create"
    },
    {
      "type": "schedule",
      "priority": 2,
      "label": "캘린더 등록",
      "action_url": "/api/v1/schedules/create"
    },
    {
      "type": "chain",
      "priority": 3,
      "label": "다음 단계 실행",
      "suggested_template": "monthly-report-followup"
    }
  ],
  "pending_count": 5,
  "last_reminder": "2026-02-23T10:00:00Z"
}
```

**개발 공수**: 1~2일 (API 조합 + 리마인더 로직)  
**난이도**: ⭐⭐☆☆☆ (쉬움)  
**우선순위**: 🔥🔥 CRITICAL  
**판정**: ✅ GO — 즉시 구현 가능, 고착화 핵심 기능

---

### 💡 Idea #279: Undo Capsule — 안전 실행 복원 캡슐

**날짜**: 2026-02-24 05:45 UTC

#### 기술적 타당성: 🟡 조건부 가능 ⭐⭐⭐☆☆

**기존 인프라 활용**:
- ✅ `task_preview.py` (실행 전 미리보기)
- ⚠️ Google API 버전 관리 필요
- ⚠️ Diff 저장 인프라 필요

**필요한 추가 구현**:
1. **버전 스냅샷 저장**: 실행 전 문서/시트/슬라이드 상태 저장
2. **Diff 계산**: 변경 전후 비교
3. **롤백 API**: Google Drive 버전 복원 또는 내용 되돌리기

**기술적 도전**:
- Google Docs/Sheets API는 버전 관리가 제한적
- Drive API의 `revisions` 사용 가능하나 세밀한 부분 복원은 어려움
- 전체 문서 롤백은 가능, 부분 롤백은 복잡

**권장 접근**:
1. **Phase 1 (MVP)**: 전체 롤백만 지원
2. **Phase 2**: 부분 롤백 (텍스트/서식 분리)

**개발 공수**: 3~5일 (MVP), 2주+ (부분 롤백)  
**난이도**: ⭐⭐⭐⭐☆ (중상)  
**우선순위**: 🟡 MEDIUM  
**판정**: ⚠️ 조건부 GO — MVP 먼저, 부분 롤백은 Phase 2

---

### 💡 Idea #280: Resume Card Deep-Link — 딥링크 기반 이어하기 카드

**날짜**: 2026-02-24 05:45 UTC

#### 기술적 타당성: 🟢 즉시 구현 가능 ⭐⭐⭐⭐⭐

**기존 인프라 활용**:
- ✅ `share.py` (공유 링크)
- ✅ `recovery-deck` API (실패 복구)
- ✅ `smart-exit-hints` API (다음 액션)
- ✅ `chain_service.py` (체인 재개)

**구현 방법**:
```python
# 알림 메시지에 포함할 딥링크
deep_link = f"agenthq://tasks/{task_id}?action=resume&context=notification"

# 웹 fallback
web_link = f"https://agenthq.io/tasks/{task_id}?action=resume"

# 모바일 Universal Links (iOS) / App Links (Android)
# apple-app-site-association, assetlinks.json 설정 필요
```

**개발 공수**: 1~2일 (딥링크 라우팅 + 모바일 설정)  
**난이도**: ⭐⭐☆☆☆ (쉬움)  
**우선순위**: 🔥 HIGH  
**판정**: ✅ GO — 즉시 구현 가능

---

### 💡 Idea #281: Friction Meter — 작업 마찰도 측정기

**날짜**: 2026-02-24 05:45 UTC

#### 기술적 타당성: 🟢 구현 가능 ⭐⭐⭐⭐☆

**기존 인프라 활용**:
- ✅ Task 실행 통계 (성공/실패/재시도)
- ✅ `analytics.py` (분석 인프라)
- ✅ `streak_service.py` (사용자 행동 패턴)

**구현 방법**:
```python
# 마찰 지수 계산 공식
friction_score = (
    (failures * 3) +
    (retries * 2) +
    (manual_interventions * 5) +
    (avg_completion_time_deviation * 1)
) / total_tasks

# 사용자별 프로필 조정
if friction_score > 0.7:
    # 확인 단계 강화
    user.confirmation_mode = "strict"
elif friction_score < 0.3:
    # 원클릭 실행
    user.confirmation_mode = "minimal"
```

**개발 공수**: 2~3일 (지표 수집 + 프로필 조정)  
**난이도**: ⭐⭐⭐☆☆ (중간)  
**우선순위**: 🟡 MEDIUM  
**판정**: ✅ GO — 개인화 핵심 기능

---

## 📊 최종 우선순위 & 실행 권고

### 즉시 구현 가능 (이번 주)

| 순위 | ID | 아이디어 | 판정 | 공수 | 오늘 가능? |
|------|-----|---------|------|------|-----------|
| **1** | #278 | Smart Follow-Through Hub | ✅ GO | 1~2일 | 🟡 |
| **2** | #276 | Reliability Landing Page | ✅ GO | 1~1.5일 | 🟡 |
| **3** | #280 | Resume Card Deep-Link | ✅ GO | 1~2일 | 🟡 |

### 다음 스프린트 (다음 주)

| 순위 | ID | 아이디어 | 판정 | 공수 | 비고 |
|------|-----|---------|------|------|------|
| **4** | #277 | Chain Progress Dock | ✅ GO (조건부) | 2~3일 | WebSocket 우선 |
| **5** | #281 | Friction Meter | ✅ GO | 2~3일 | 개인화 핵심 |
| **6** | #279 | Undo Capsule | ⚠️ 조건부 GO | 3~5일 | MVP 먼저 |

---

## 💬 개발자 가이드

### P0 (즉시 조치 필요)

1. **Chain 실행 완성**
   ```python
   # backend/app/services/chain_service.py
   def _execute_current_step(self, chain, db):
       # 기존: Task 생성까지만
       task = create_task(...)
       
       # 추가 필요: Celery 큐 투입
       from app.agents.celery_app import process_docs_task
       process_docs_task.apply_async(args=[str(task.id)])
   ```

2. **모델 마이그레이션 가시성**
   ```python
   # backend/app/models/__init__.py
   from .task_chain import TaskChain
   from .scheduled_task import ScheduledTask
   
   # backend/alembic/env.py
   from app.models import TaskChain, ScheduledTask
   ```

3. **사용자 활동 추적**
   ```python
   # 모든 Task 생성 경로에서
   user.last_task_created_at = datetime.utcnow()
   db.commit()
   ```

### P1 (이번 주 완료)

- #278 Smart Follow-Through Hub
- #276 Reliability Landing Page
- #280 Resume Card Deep-Link

### P2 (다음 스프린트)

- #277 Chain Progress Dock (WebSocket 구축)
- #281 Friction Meter
- #279 Undo Capsule (MVP)

---

## 🎯 기획자 피드백

### ✅ 잘하고 있는 것

1. **실행 중심 사고**
   - Phase 40 이후 아이디어 생성 속도 조절
   - Quick Win 중심의 제안

2. **기존 인프라 활용**
   - 신규 아이디어가 기존 API를 80%+ 활용
   - 개발 효율성 극대화

3. **사용자 경험 중심**
   - 실패 → 복구 → 성공의 전체 여정 커버

### 💡 발전 제안

1. **Phase 별 테마 명확화**
   - Phase 51: "실행 연속성" (Resume, Follow-Through, Deep-Link)
   - Phase 52: "실행 신뢰성" (Undo, Friction Meter, Progress Dock)

2. **Quick Win 정의 명확화**
   - 🟢 1일 이내: 즉시 실행
   - 🟡 2~3일: 이번 주 완료
   - 🔴 1주 이상: 다음 스프린트

3. **기술 검토 단계 강화**
   - 아이디어 제안 시 "기존 API" 섹션 포함
   - 예: "#278은 smart-exit-hints + share + schedules 조합"

---

## 📈 전체 프로젝트 건강 지표

| 지표 | 값 | 트렌드 | 평가 |
|------|-----|--------|------|
| 총 아이디어 | 281개 | 📈 | 풍부 |
| 배포된 기능 | 20+개 | 📈 | 가속 중 |
| 테스트 함수 | 2,400+개 | 📈 | 우수 |
| 코드 규모 | ~85,000줄 | 📈 | 안정 |
| 실행 비율 | ~10% | 📈 | 개선 중 |
| 개발 속도 | 3,000줄/일 | 📈 | 매우 빠름 |

**종합 평가**: ⭐⭐⭐⭐⭐ 탁월

**핵심 메시지**: 
- 최근 48시간 개발 속도가 역대 최고 수준
- 에러 처리 인프라가 완성되어 신뢰성 기반 구축 완료
- 신규 아이디어 6개 모두 기술적으로 타당하며, 3개는 즉시 구현 가능
- Quick Win 중심으로 이번 주에 3개 배포 가능

---

**작성 완료**: 2026-02-24 10:14 UTC  
**다음 검토**: 2026-02-25 또는 Phase 52 아이디어 추가 시  
**리뷰어**: Architect Agent

---

## 이전 검토 이력

- 2026-02-23 07:40: Phase 40 검토 (#267~#269)
- 2026-02-19 06:39: Phase 37-39 검토 (#211~#219)
- 2026-02-17 11:25: Phase 18 검토 (#154~#156)
- 2026-02-12 07:57: Phase 7-8 검토 (7개 아이디어)
