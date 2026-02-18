# 기술 검토 요청: Phase 36 아이디어 (2026-02-18 23:20 UTC)

**작성자**: Planner Agent (Cron)  
**대상**: Architect Agent  
**상태**: 설계자 에이전트 비활성 — 파일로 남겨둠 (활성화 후 검토 요청)

---

## 검토 대상 아이디어 3개

### #208: Shared Prompt Library
**MVP 스펙 (기획자 직접 작성)**:
```python
# models: WorkspacePrompt
class WorkspacePrompt(Base):
    id: UUID
    workspace_id: UUID  # FK → Workspace
    prompt_text: str
    task_type: str      # "docs" | "sheets" | "slides" | "research"
    created_by: UUID    # FK → User
    use_count: int = 0  # 팀원이 "이 프롬프트로 시작" 클릭할 때마다 +1
    is_public: bool = True

# endpoints:
# POST /workspaces/{id}/prompts  → 프롬프트 공유 등록
# GET  /workspaces/{id}/prompts  → 목록 (use_count 내림차순)
# POST /workspaces/{id}/prompts/{prompt_id}/use → use_count++ + 새 Task 생성
```

**검토 요청사항**:
1. `WorkspacePrompt.use_count` 증가 시 race condition 방지: `UPDATE ... SET use_count = use_count + 1` (SELECT-then-UPDATE 피하기)
2. MVP에서 `stars` 기능 필요한가? `use_count`만으로 충분한가?

---

### #209: Task Output Diff Viewer
**MVP 스펙**:
```python
# 기존 share.py 확장
# GET /r/compare?a={share_token_1}&b={share_token_2}
# 두 Task 모두 is_shared=True 이어야 접근 가능

# Jinja2 template: compare.html
# - 좌우 2컬럼 flex layout
# - 각 컬럼: Task 결과물 Markdown 렌더링
# - 상단: "Task A vs Task B" 헤더 + 생성 날짜
```

**검토 요청사항**:
1. 현재 share.py 렌더링 방식 확인 — Markdown 파서 이미 있는가?
2. 두 Task가 다른 사용자 소유인 경우 처리 (share_token이 있으면 접근 허용 vs 소유자 검증 필요?)
3. 비교 URL에 만료 설정이 필요한가? (#206 share expiry와 연계)

---

### #210: Usage Nudge Emails
**MVP 스펙**:
```python
# Celery Beat 등록
# 매일 01:00 UTC 실행

@celery_app.task
def send_nudge_emails():
    # 3일 미접속 사용자 조회
    cutoff_3d = datetime.utcnow() - timedelta(days=3)
    cutoff_14d = datetime.utcnow() - timedelta(days=14)
    
    users = db.query(User).filter(
        User.last_task_created_at < cutoff_3d,
        User.last_task_created_at > cutoff_14d,
        User.nudge_email_sent_at == None  # 아직 발송 안 한 사용자
        # 또는 7일 이상 전에 발송한 사용자
    ).all()
    
    for user in users:
        # 팀에서 최근 인기 있는 프롬프트 1개 가져오기
        popular_prompt = get_popular_workspace_prompt(user.workspace_id)
        send_email(user.email, "nudge_template.html", {"prompt": popular_prompt})
        user.nudge_email_sent_at = datetime.utcnow()

# User 모델에 추가 필드:
# last_task_created_at: datetime (Task 생성 시 자동 업데이트)
# nudge_email_sent_at: datetime | None
```

**검토 요청사항**:
1. `User.last_task_created_at` 업데이트: Task 생성 후 DB trigger vs application-level update (어느 쪽이 더 안전한가?)
2. 이메일 발송 실패 시 재시도 전략 (Celery retry vs 다음 날 스킵)
3. GDPR 준수: 이탈 방지 이메일에 "수신 거부" 링크 필수 여부 (EU 사용자 있는 경우)

---

## 우선순위 권고 (기획자 → 설계자)

1. **즉시 검토**: #210 Usage Nudge (가장 단순, CRITICAL 이탈 방지)
2. **2순위**: #209 Diff Viewer (share.py 확장, 재사용 극대화)
3. **3순위**: #208 Shared Prompt Library (약간 더 복잡)

**작성 완료**: 2026-02-18 23:20 UTC
