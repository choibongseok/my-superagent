# Sprint 2: Usage Nudge Email Scheduler - 2026-03-02

## 🎯 목표
#210 Usage Nudge Emails 작업 완료 - Celery Beat 스케줄러 설정 추가

## ✅ 완료 작업

### 1. 기존 구현 확인
- ✅ `backend/app/tasks/nudge_email.py` - 완전히 구현됨
  - `send_usage_nudge_emails()` Celery task
  - 7일 비활성 사용자 감지 (`_get_inactive_users()`)
  - `last_task_created_at` 기준 (Task.created_at)
  - 주 최대 2통 제한 (`_can_send_nudge_email()`)
  - DB 로깅 (`_record_nudge_email()`)
  - 개발용 테스트 task (`test_nudge_email()`)

- ✅ `backend/app/models/nudge_email_log.py` - DB 모델 완성
  - `NudgeEmailLog` 모델 (user_id, email_type, sent_at, success, error_message)
  - User 관계 설정 (back_populates)
  - Weekly limit 추적용 인덱스

- ✅ Alembic migrations 존재
  - `003_nudge_email_logs.py`
  - `210_add_nudge_email_fields.py`
  - `212_add_nudge_week_tracking.py`

### 2. Celery Beat 스케줄러 설정 추가
```python
# backend/app/tasks/scheduled_tasks.py

# Import 추가
from app.tasks.nudge_email import send_usage_nudge_emails

# Periodic task 등록
@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    # ... 기존 task ...
    
    # 매일 10:00 AM UTC에 nudge email 발송
    from celery.schedules import crontab
    sender.add_periodic_task(
        crontab(hour=10, minute=0),
        send_usage_nudge_emails.s(days_inactive=7),
        name="Send daily usage nudge emails"
    )
```

### 3. Git Commit
```bash
git add backend/app/tasks/scheduled_tasks.py
git commit -m "#210 Add usage nudge email periodic task

- Add daily nudge email task (10:00 AM UTC) to Celery Beat
- Automatically sends emails to users inactive for 7+ days
- Max 2 emails per user per week (enforced by DB)
- Nudge email implementation already complete in nudge_email.py"
```

**Commit Hash**: `6ce70d18`

## 📊 구현 상세

### Nudge Email 워크플로우

1. **스케줄링**
   - Celery Beat가 매일 10:00 AM UTC에 `send_usage_nudge_emails` task 트리거
   - `days_inactive=7` 파라미터로 7일 비활성 사용자 타겟팅

2. **비활성 사용자 감지**
   ```sql
   -- Task 테이블에서 각 user의 최근 task 생성일 조회
   SELECT user_id, MAX(created_at) as last_task_at
   FROM tasks
   GROUP BY user_id
   
   -- 7일 이상 task 생성 안 한 활성 사용자 조회
   SELECT users.*
   FROM users
   LEFT JOIN (subquery) ON users.id = subquery.user_id
   WHERE users.is_active = true
     AND (subquery.last_task_at IS NULL 
          OR subquery.last_task_at < NOW() - INTERVAL '7 days')
   ```

3. **주간 제한 체크**
   ```sql
   -- 이번 주(월요일 00:00 ~ 현재) 발송된 nudge email 카운트
   SELECT COUNT(*)
   FROM nudge_email_logs
   WHERE user_id = :user_id
     AND sent_at >= :week_start
     AND email_type = 'usage_nudge'
   
   -- 2통 미만이면 발송 가능
   ```

4. **이메일 발송**
   - Beautiful HTML 템플릿 (gradient header, feature highlights, CTA button)
   - Text fallback (plain text version)
   - Subject: "We miss you at AgentHQ! 🚀"
   - Content: 신규 기능 소개 (Sheets/Slides agents, improved research, memory)

5. **DB 로깅**
   ```python
   NudgeEmailLog(
       user_id=user.id,
       email_type="usage_nudge",
       sent_at=datetime.utcnow(),
       success=True/False,
       error_message=None or "SMTP error"
   )
   ```

### 의존성

**모델**:
- `User` (users 테이블) - 이메일 수신자
- `Task` (tasks 테이블) - 활동 추적 (created_at)
- `NudgeEmailLog` (nudge_email_logs 테이블) - 발송 이력

**서비스**:
- `email_service` (app.services.email_service) - 실제 SMTP 발송
- `AsyncSessionLocal` - 비동기 DB 세션
- `run_async()` - async/await → Celery 동기 브릿지

**Celery**:
- `celery_app` (app.agents.celery_app) - Task 등록
- `celery.schedules.crontab` - Cron 스케줄

## 🧪 테스트 방법

### 1. 로컬 테스트 (단일 이메일)
```bash
# Python shell에서 테스트 task 실행
python
>>> from app.tasks.nudge_email import test_nudge_email
>>> result = test_nudge_email.delay('user@example.com')
>>> result.get()
{'status': 'success', 'message': 'Test email sent to user@example.com'}
```

### 2. Celery Worker 시작
```bash
# Terminal 1: Celery worker
celery -A app.agents.celery_app worker --loglevel=info

# Terminal 2: Celery beat (scheduler)
celery -A app.agents.celery_app beat --loglevel=info
```

### 3. 수동 실행
```bash
# Python shell
>>> from app.tasks.nudge_email import send_usage_nudge_emails
>>> result = send_usage_nudge_emails.delay(days_inactive=7)
>>> result.get()
{
    'status': 'completed',
    'total_inactive': 5,
    'emails_sent': 3,
    'emails_skipped': 2,
    'errors': []
}
```

### 4. DB 검증
```bash
# PostgreSQL
psql -d agenthq

-- 발송 이력 확인
SELECT 
    nel.id,
    u.email,
    nel.email_type,
    nel.sent_at,
    nel.success,
    nel.error_message
FROM nudge_email_logs nel
JOIN users u ON nel.user_id = u.id
ORDER BY nel.sent_at DESC
LIMIT 10;

-- 주간 발송 카운트
SELECT 
    u.email,
    COUNT(*) as emails_this_week
FROM nudge_email_logs nel
JOIN users u ON nel.user_id = u.id
WHERE nel.sent_at >= date_trunc('week', NOW())
  AND nel.email_type = 'usage_nudge'
GROUP BY u.email
ORDER BY emails_this_week DESC;
```

## 📈 예상 효과

### 사용자 재활성화
- **타겟**: 7일 이상 비활성 사용자
- **목표**: 20-30% 재활성화율
- **주기**: 주 최대 2통 (과도한 스팸 방지)

### 이메일 전환율
- **Open rate**: 30-40% (engaging subject line)
- **Click-through rate**: 10-15% (prominent CTA button)
- **Unsubscribe rate**: <2% (주간 제한으로 억제)

### 비즈니스 임팩트
- Retention 개선 (churn 감소)
- DAU/MAU 증가
- User lifetime value 증대

## ⚠️ 주의사항

### 1. SMTP 설정 필요
`email_service`가 동작하려면 환경변수 설정 필수:
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@agenthq.com
SMTP_PASSWORD=***
SMTP_FROM_EMAIL=noreply@agenthq.com
SMTP_FROM_NAME=AgentHQ Team
```

### 2. Rate Limiting
- 대량 발송 시 SMTP provider rate limit 주의
- Gmail: 500 emails/day (free), 2000/day (Google Workspace)
- 필요시 SendGrid/AWS SES로 전환

### 3. Unsubscribe 기능
현재 미구현 - Phase 2에서 추가 예정:
- `User.email_preferences` JSON 필드
- Unsubscribe link in email footer
- Preference center UI

### 4. 모니터링
Celery Flower 또는 LangFuse로 모니터링 권장:
```bash
# Celery Flower (web UI)
celery -A app.agents.celery_app flower
# http://localhost:5555
```

## 🚀 다음 단계

### Phase 2.1: Nudge Email 개선
- [ ] A/B 테스트 (subject lines, 발송 시간)
- [ ] 개인화 (user's last task, 추천 task)
- [ ] Unsubscribe 기능
- [ ] Weekly digest 옵션

### Phase 2.2: 다른 Nudge 타입
- [ ] Onboarding nudge (가입 후 0 tasks)
- [ ] Feature announcement nudge
- [ ] Upgrade nudge (free → paid)
- [ ] Win-back nudge (30+ days 비활성)

## 🎉 결과

- ✅ #210 Usage Nudge Emails 완료
- ✅ Celery Beat 스케줄러 설정 완료
- ✅ 매일 10:00 AM UTC 자동 발송
- ✅ 7일 비활성 + 주 최대 2통 제한
- ✅ Git commit 완료 (6ce70d18)

**Status**: ✅ **Complete**
**Time**: ~30 minutes
**LOC Changed**: +10 lines (scheduled_tasks.py)
**Dependencies**: All pre-implemented (nudge_email.py, models, migrations)

---

**작성자**: Implementer Agent  
**작성일**: 2026-03-02 06:38 UTC  
**관련 이슈**: #210 Usage Nudge Emails  
**Commit**: 6ce70d18
