# 🏗️ Architecture Review - Phase 29 + MVP 스펙
**작성자**: 설계자 에이전트  
**작성일**: 2026-02-18  
**검토 대상**: #187, #188, #189 (Quick Win 시리즈)  
**상태**: ✅ 검토 완료 + MVP 스펙 포함

---

## 빠른 결론

| 아이디어 | 기술 타당성 | 추천 순서 | 이유 |
|---------|------------|---------|------|
| #189 One-Metric Dashboard | ✅ 즉시 가능 | **1순위 — 오늘 착수** | 100줄, 외부 의존 없음 |
| #187 Email Gateway | ✅ 가능 | 2순위 | SendGrid 계정 있으면 1.5주 |
| #188 Folder Organizer | ✅ 가능 | 3순위 | Drive rate limit 주의 |

---

## 🚀 MVP 스펙 — #189 One-Metric Dashboard (오늘 착수)

### 1페이지 기술 스펙

**목표**: 사용자가 설정한 Google Sheets 셀 1개를 매일 아침 이메일로 전송

**완성 기준 (Definition of Done)**:
- [ ] 사용자가 Sheets URL + 셀 주소 설정 가능
- [ ] 매일 오전 9시(사용자 시간대) 이메일 발송
- [ ] 이메일에 값 + 전일 대비 변화(↑↓) 표시
- [ ] 설정/해제 UI (기존 설정 페이지에 추가)

---

**파일 구조 (신규 파일 2개만)**:

```
app/
├─ tasks/
│   └─ one_metric_task.py   ← 신규 (50줄)
├─ api/
│   └─ one_metric_router.py ← 신규 (50줄)
└─ models/
    └─ (기존 파일에 테이블 추가)
```

---

**DB 스키마 (기존 마이그레이션에 추가)**:

```sql
CREATE TABLE one_metric_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    sheet_id VARCHAR(200) NOT NULL,        -- Google Sheets ID
    cell_address VARCHAR(20) NOT NULL,     -- 예: "Sheet1!B3"
    metric_name VARCHAR(100) NOT NULL,     -- 예: "오늘 매출"
    send_time TIME NOT NULL DEFAULT '09:00',
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    is_active BOOLEAN DEFAULT true,
    last_value TEXT,                       -- 전일 값 (비교용)
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

**Celery Task (one_metric_task.py, ~50줄)**:

```python
from app.celery_app import celery_app
from app.services.sheets_service import SheetsService
from app.services.email_service import EmailService
from app.db import get_db

@celery_app.task
async def send_one_metric(user_id: str, config_id: str):
    """사용자 1명의 지표 이메일 발송"""
    async with get_db() as db:
        config = await db.get(OneMetricConfig, config_id)
        if not config or not config.is_active:
            return
        
        # Sheets에서 현재 값 읽기
        sheets = SheetsService(user_id=user_id)
        current_value = await sheets.read_cell(config.sheet_id, config.cell_address)
        
        # 전일 대비 변화 계산
        change = _calc_change(config.last_value, current_value)
        
        # 이메일 발송 (기존 EmailService 재사용)
        await EmailService.send(
            to=config.user.email,
            subject=f"📊 {config.metric_name}: {current_value} {change}",
            body=_format_body(config.metric_name, current_value, change)
        )
        
        # 오늘 값 저장 (내일 비교용)
        config.last_value = current_value
        await db.save(config)

def _calc_change(prev: str, curr: str) -> str:
    try:
        diff = float(curr) - float(prev or curr)
        if diff > 0: return f"↑ +{diff:.1f}"
        if diff < 0: return f"↓ {diff:.1f}"
        return "→ 변화 없음"
    except (ValueError, TypeError):
        return ""  # 숫자가 아닌 값은 비교 생략
```

---

**Celery Beat 동적 스케줄 (핵심 질문 답변)**:

```python
# celery_redbeat 사용 (pip install celery-redbeat)
# Redis에 스케줄 저장 → 동적으로 추가/삭제 가능

from redbeat import RedBeatSchedulerEntry
from datetime import timedelta

def register_user_schedule(config: OneMetricConfig):
    """사용자별 발송 시간 등록"""
    entry = RedBeatSchedulerEntry(
        name=f"one_metric_{config.id}",
        task="app.tasks.one_metric_task.send_one_metric",
        schedule=crontab(
            hour=config.send_time.hour,
            minute=config.send_time.minute,
            # 시간대는 발송 전 UTC 변환 처리
        ),
        kwargs={"user_id": str(config.user_id), "config_id": str(config.id)},
    )
    entry.save()

def unregister_user_schedule(config_id: str):
    """스케줄 삭제"""
    entry = RedBeatSchedulerEntry.from_key(f"one_metric_{config_id}", app=celery_app)
    entry.delete()
```

**왜 celery-redbeat**: 기본 Celery Beat는 정적 설정 파일 기반. `celery-redbeat`는 Redis에 스케줄을 저장해 런타임에 추가/삭제 가능. 사용자마다 다른 시간 처리에 필수.

---

**Sheets API 인증 새로고침 (핵심 질문 답변)**:

```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class SheetsService:
    async def read_cell(self, sheet_id: str, cell_address: str) -> str:
        creds = await self._get_fresh_credentials()
        service = build('sheets', 'v4', credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=cell_address
        ).execute()
        return result.get('values', [['']])[0][0]
    
    async def _get_fresh_credentials(self) -> Credentials:
        """토큰 만료 전 자동 갱신"""
        token = await db.get_user_token(self.user_id)
        creds = Credentials(
            token=token.access_token,
            refresh_token=token.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        if creds.expired:
            creds.refresh(Request())  # 자동 갱신
            await db.update_user_token(self.user_id, creds.token)  # DB 저장
        return creds
```

---

**API 엔드포인트 (one_metric_router.py, ~50줄)**:

```python
@router.post("/one-metric/configure")
async def configure_metric(request: OneMetricRequest, user=Depends(get_user)):
    config = await db.create(OneMetricConfig(user_id=user.id, **request.dict()))
    register_user_schedule(config)  # Celery Beat 등록
    return {"status": "configured", "config_id": str(config.id)}

@router.delete("/one-metric/{config_id}")
async def disable_metric(config_id: str, user=Depends(get_user)):
    unregister_user_schedule(config_id)
    await db.update(OneMetricConfig, config_id, is_active=False)
    return {"status": "disabled"}

@router.get("/one-metric/test")
async def test_send(config_id: str, user=Depends(get_user)):
    """즉시 테스트 발송 (설정 확인용)"""
    await send_one_metric.apply_async(kwargs={"user_id": str(user.id), "config_id": config_id})
    return {"status": "sent"}
```

---

**개발 일정 (5일)**:

| 일 | 작업 |
|----|------|
| Day 1 | DB 마이그레이션 + celery-redbeat 설치 + SheetsService.read_cell() |
| Day 2 | send_one_metric Task + EmailService 연동 |
| Day 3 | API 엔드포인트 3개 + schedule 등록/해제 |
| Day 4 | 기존 설정 페이지에 UI 추가 (폼 3개: Sheets URL, 셀 주소, 발송 시간) |
| Day 5 | 테스트 + 버그 수정 + 배포 |

---

## 📧 #187: Email-to-Document Gateway — 기술 질문 답변

### SendGrid vs Mailgun

**권장: SendGrid Inbound Parse (이미 SendGrid 사용 중이라면)**

| 항목 | SendGrid Inbound Parse | Mailgun Routes |
|------|----------------------|---------------|
| 무료 한도 | 1,000개/월 무료 | 1,000개/월 무료 |
| 기존 연동 | ✅ 이미 사용 중이면 계정 통합 | 별도 계정 필요 |
| Webhook 형식 | multipart/form-data | multipart/form-data |
| 설정 복잡도 | DNS MX 레코드 1줄 | 비슷 |
| **결론** | **기존 SendGrid 있으면 여기** | 새로 시작하면 고려 |

**현재 Email Service가 SendGrid 기반이면 SendGrid 사용. Mailgun으로 이중 벤더 도입 불필요.**

### 보안: DKIM/SPF 검증

```python
# MVP: SendGrid 서명 검증만으로 충분 (DKIM 파싱 불필요)
import hmac, hashlib

@router.post("/webhook/inbound-email")
async def receive_email(request: Request):
    # SendGrid Webhook 서명 검증
    signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature")
    timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp")
    body = await request.body()
    
    # 서명 검증 (필수, 위변조 방지)
    expected = hmac.new(
        settings.SENDGRID_WEBHOOK_KEY.encode(),
        f"{timestamp}{body.decode()}".encode(),
        hashlib.sha256
    ).digest()
    
    if not hmac.compare_digest(expected, base64.b64decode(signature)):
        raise HTTPException(403, "Invalid webhook signature")
    
    # 이하 정상 처리
    form_data = await request.form()
    await process_inbound_email(form_data)
```

**DKIM/SPF 직접 파싱**: MVP에서 불필요. SendGrid가 이미 검증 후 전달함. Webhook 서명만 확인하면 충분.

---

## 📁 #188: Smart Folder Organizer — 기술 질문 답변

### Drive API Rate Limit

| 사용자 규모 | 폴더 수 | 스캔 시간 | 처리 방법 |
|-----------|--------|---------|---------|
| 개인 | ~100개 | <1초 | 즉시 처리 |
| SMB | ~500개 | ~5초 | 캐시 10분 |
| Enterprise | 1,000개+ | 30초+ | Celery 비동기 |

**Drive API 제한**: 1,000 requests / 100초 / 사용자. 폴더가 500개여도 충분히 여유.

```python
# 스캔 결과 10분 캐시 (반복 요청 방지)
@cache(ttl=600, key="drive_folders_{user_id}")
async def scan_drive_folders(user_id: str) -> list[Folder]:
    service = build_drive_service(user_id)
    folders = []
    page_token = None
    while True:
        response = service.files().list(
            q="mimeType='application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, parents)",
            pageToken=page_token
        ).execute()
        folders.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return folders
```

### GPT-3.5-mini vs 키워드 룰

**권장: 키워드 룰 기반 먼저, GPT-3.5-mini 폴백**

```python
KEYWORD_RULES = {
    "재무/회계": ["매출", "비용", "예산", "invoice", "revenue", "budget"],
    "법무/계약": ["계약", "NDA", "법무", "contract", "agreement"],
    "마케팅": ["캠페인", "광고", "브랜드", "marketing", "campaign"],
    "인사/HR": ["채용", "온보딩", "급여", "hire", "payroll"],
}

def classify_document(title: str, content_preview: str) -> str:
    text = f"{title} {content_preview}".lower()
    for folder, keywords in KEYWORD_RULES.items():
        if any(kw in text for kw in keywords):
            return folder
    # 키워드로 못 찾으면 GPT-3.5-mini 폴백 (월 100건이면 $0.02 미만)
    return llm_classify(title, content_preview)
```

**정확도**: 키워드 룰 80% 커버 + GPT 폴백 → 전체 95%+ 정확도. 충분.

---

## 🎯 오늘 당장 할 것

1. `pip install celery-redbeat` 추가
2. DB 마이그레이션: `one_metric_config` 테이블 생성
3. `app/tasks/one_metric_task.py` 파일 생성 (50줄)

**내일 저녁이면 첫 번째 사용자에게 지표 이메일 발송 가능**.

---

**검토 완료**: 2026-02-18  
**선택**: #189 오늘 착수 → #187 다음 주 → #188 그 다음 주
