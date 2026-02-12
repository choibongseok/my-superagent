# 🔧 개발자 에이전트 - 즉시 조치 사항

**전달자**: 설계자 에이전트  
**수신자**: 개발자 에이전트  
**날짜**: 2026-02-12  
**우선순위**: CRITICAL

---

## ⚠️ CRITICAL - 즉시 수정 필요 (6시간)

### 1. Memory Buffer AttributeError 수정 (2시간)

**문제:**
```python
AttributeError: 'ConversationMemory' object has no attribute 'buffer'
```

**수정할 파일:**

#### 파일 1: `backend/app/memory/conversation.py`
**위치**: Line 229  
**현재 코드:**
```python
@property
def buffer(self):
    return self.memory
```

**수정 후:**
```python
@property
def langchain_memory(self):  # 이름 변경
    """Get the underlying LangChain memory object for agent integration."""
    return self.memory
```

#### 파일 2: `backend/app/agents/base.py`
**위치**: Line 248  
**현재 코드:**
```python
self.agent_executor = AgentExecutor(
    agent=agent,
    tools=self.tools,
    memory=self.memory.buffer,  # ❌ 오류
    ...
)
```

**수정 후:**
```python
self.agent_executor = AgentExecutor(
    agent=agent,
    tools=self.tools,
    memory=self.memory.langchain_memory,  # ✅ 수정
    verbose=settings.DEBUG,
    max_iterations=10,
    max_execution_time=300,
    callbacks=callbacks,
    handle_parsing_errors=True,
    return_intermediate_steps=True,
)
```

**테스트:**
```bash
cd backend
pytest tests/agents/test_base_agent.py -v
pytest tests/agents/test_research_agent.py -v
```

---

### 2. Alembic Migration UUID Import 추가 (1시간)

**문제:**
```
NameError: name 'uuid' is not defined
```

**수정할 파일:**

#### `backend/alembic/versions/c4d39e6ece1f_add_chat_and_message_models.py`
**위치**: Line 10 (import 섹션)  
**현재 코드:**
```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
```

**수정 후:**
```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid  # ✅ 추가
```

**테스트:**
```bash
cd backend
alembic upgrade head
# 에러 없이 실행되어야 함
```

---

### 3. Celery Async 함수 처리 수정 (3시간)

**문제:**
```python
# Celery task에서 async 함수를 await 없이 호출
result = agent.run(prompt)  # ❌ RuntimeWarning
```

**수정할 파일:**

#### `backend/app/agents/celery_app.py`
**전체 파일 리팩토링 필요**

**현재 구조 (예상):**
```python
@celery_app.task
def run_research_task(user_id, session_id, prompt):
    agent = ResearchAgent(user_id, session_id)
    result = agent.run(prompt)  # ❌ await 없음
    return result
```

**수정 후:**
```python
import asyncio
from app.agents.research_agent import ResearchAgent
from app.agents.docs_agent import DocsAgent
# ... 기타 Agent import

@celery_app.task
def run_research_task(user_id: str, session_id: str, prompt: str):
    """Research Agent 실행 (비동기 래퍼)"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        _run_research_async(user_id, session_id, prompt)
    )

async def _run_research_async(user_id: str, session_id: str, prompt: str):
    """실제 비동기 Research Agent 실행"""
    agent = ResearchAgent(user_id, session_id)
    result = await agent.run(prompt)  # ✅ await 사용
    return result

@celery_app.task
def run_docs_task(user_id: str, session_id: str, prompt: str):
    """Docs Agent 실행 (비동기 래퍼)"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        _run_docs_async(user_id, session_id, prompt)
    )

async def _run_docs_async(user_id: str, session_id: str, prompt: str):
    """실제 비동기 Docs Agent 실행"""
    agent = DocsAgent(user_id, session_id)
    result = await agent.run(prompt)  # ✅ await 사용
    return result

# 나머지 Agent도 동일 패턴 적용
```

**또는 Celery 5.3+ 네이티브 async 지원 (더 깔끔):**
```python
from celery import Celery

celery_app = Celery("agenthq")

@celery_app.task
async def run_research_task(user_id: str, session_id: str, prompt: str):
    """Celery 5.3+ async task"""
    agent = ResearchAgent(user_id, session_id)
    result = await agent.run(prompt)  # ✅ 직접 await
    return result
```

**테스트:**
```bash
# Celery worker 시작
celery -A app.agents.celery_app worker --loglevel=info

# 별도 터미널에서 task 실행
python -c "
from app.agents.celery_app import run_research_task
result = run_research_task.delay('user123', 'session456', 'Test query')
print(result.get(timeout=30))
"
```

---

## 🟡 HIGH PRIORITY - 1주 내 완료 (24시간)

### 4. Google Sheets Agent 구현 (8시간)

**파일:**
- `backend/app/tools/google_apis.py` (확장)
- `backend/app/agents/sheets_agent.py` (완성)

**작업:**
1. Google Sheets API Tool 구현
   ```python
   class GoogleSheetsAPI:
       def __init__(self, credentials):
           self.service = build('sheets', 'v4', credentials=credentials)
       
       def create_spreadsheet(self, title: str) -> dict:
           ...
       
       def add_data(self, spreadsheet_id: str, range: str, values: List[List]) -> dict:
           ...
       
       def format_cells(self, spreadsheet_id: str, ...) -> dict:
           ...
   ```

2. SheetsAgent 완성
   ```python
   class SheetsAgent(BaseAgent):
       def _create_tools(self) -> List[Tool]:
           sheets_api = GoogleSheetsAPI(self.credentials)
           
           return [
               StructuredTool.from_function(
                   func=sheets_api.create_spreadsheet,
                   name="create_spreadsheet",
                   description="Create a new Google Spreadsheet with title",
               ),
               StructuredTool.from_function(
                   func=sheets_api.add_data,
                   name="add_data_to_sheet",
                   description="Add data rows to a spreadsheet",
               ),
               StructuredTool.from_function(
                   func=sheets_api.format_cells,
                   name="format_cells",
                   description="Apply formatting to cells",
               ),
           ]
   ```

**테스트:**
```bash
pytest tests/agents/test_sheets_agent.py -v
```

---

### 5. Google Slides Agent 구현 (4시간)

**파일:**
- `backend/app/tools/google_apis.py` (확장)
- `backend/app/agents/slides_agent.py` (완성)

**작업:**
1. Google Slides API Tool 구현
2. SlidesAgent 완성 (Sheets와 유사 패턴)

**테스트:**
```bash
pytest tests/agents/test_slides_agent.py -v
```

---

### 6. Google Credentials 관리 (4시간)

**문제:**
- Agent 초기화 시 OAuth credentials 전달 안 됨

**새 파일 생성:** `backend/app/services/google_auth.py`

```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from app.models.user import User

async def get_google_credentials(user_id: str) -> Credentials:
    """
    사용자의 Google OAuth credentials 가져오기
    
    - DB에서 access_token, refresh_token 조회
    - 만료 시 자동 갱신
    - 갱신된 토큰 DB 저장
    """
    user = await get_user(user_id)
    
    credentials = Credentials(
        token=user.google_access_token,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    
    # 토큰 만료 시 갱신
    if credentials.expired:
        credentials.refresh(Request())
        
        # DB 업데이트
        await update_user_tokens(
            user_id=user_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
        )
    
    return credentials

async def create_agent_with_credentials(
    agent_class,
    user_id: str,
    session_id: str,
):
    """Credentials가 포함된 Agent 생성 헬퍼"""
    credentials = await get_google_credentials(user_id)
    
    agent = agent_class(
        user_id=user_id,
        session_id=session_id,
        credentials=credentials,  # ✅ 전달
    )
    
    return agent
```

**User 모델 수정:** `backend/app/models/user.py`
```python
class User(Base):
    ...
    # 추가 컬럼
    google_access_token = Column(String, nullable=True)
    google_refresh_token = Column(String, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)
```

**마이그레이션 생성:**
```bash
cd backend
alembic revision --autogenerate -m "add_google_tokens_to_user"
alembic upgrade head
```

**Agent 기본 클래스 수정:** `backend/app/agents/base.py`
```python
class BaseAgent(ABC):
    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        credentials: Optional[Credentials] = None,  # ✅ 추가
        **kwargs,
    ):
        ...
        self.credentials = credentials
```

**테스트:**
```bash
pytest tests/services/test_google_auth.py -v
```

---

### 7. Agent 단위 테스트 작성 (4시간)

**새 파일 생성:**
- `backend/tests/agents/test_sheets_agent.py`
- `backend/tests/agents/test_slides_agent.py`
- `backend/tests/services/test_google_auth.py`

**예시: `test_sheets_agent.py`**
```python
import pytest
from app.agents.sheets_agent import SheetsAgent

@pytest.mark.asyncio
async def test_sheets_agent_initialization():
    agent = SheetsAgent(user_id="test", session_id="test")
    assert agent is not None
    assert len(agent.tools) > 0

@pytest.mark.asyncio
async def test_create_spreadsheet():
    agent = SheetsAgent(user_id="test", session_id="test")
    result = await agent.run("Create a spreadsheet titled 'Q4 Sales'")
    
    assert result["success"] is True
    assert "spreadsheet_id" in result["output"]

@pytest.mark.asyncio
async def test_add_data_to_sheet():
    agent = SheetsAgent(user_id="test", session_id="test")
    result = await agent.run(
        "Add data [['Name', 'Sales'], ['Alice', 100], ['Bob', 200]] "
        "to spreadsheet 'Q4 Sales'"
    )
    
    assert result["success"] is True
```

---

## 🟢 MEDIUM PRIORITY - 2주 내 완료

### 8. MemoryManager Agent 통합 (4시간)
### 9. VectorMemory 활성화 (4시간)
### 10. Citation Tracker 통합 (4시간)

(자세한 내용은 `docs/architecture-review.md` 참고)

---

## ✅ 체크리스트

### Day 1 (Critical Fixes - 6시간)
- [ ] Memory buffer 오류 수정 (2h)
- [ ] Alembic UUID import 추가 (1h)
- [ ] Celery async 처리 수정 (3h)
- [ ] 전체 테스트 실행 및 통과 확인

### Day 2-4 (Sheets/Slides Agent - 16시간)
- [ ] Google Sheets Tool 구현 (4h)
- [ ] SheetsAgent 완성 (4h)
- [ ] Google Slides Tool 구현 (2h)
- [ ] SlidesAgent 완성 (2h)
- [ ] Google Credentials 관리 (4h)

### Day 5 (테스트 및 검증 - 4시간)
- [ ] 단위 테스트 작성 및 실행
- [ ] 통합 테스트 실행
- [ ] E2E 워크플로우 테스트
- [ ] 코드 리뷰 및 문서 업데이트

---

## 📚 참고 문서

1. **상세 아키텍처 분석**: `docs/architecture-review.md`
2. **한국어 요약**: `docs/architecture-summary-ko.md`
3. **LangChain 문서**: https://python.langchain.com/docs/
4. **Google Workspace API**: https://developers.google.com/workspace

---

## 🤝 협업 프로세스

1. **코드 작성 후**:
   - 테스트 작성 및 실행
   - Git commit with descriptive message
   - PR 생성 (검토자 에이전트 태그)

2. **PR 템플릿**:
   ```markdown
   ## 변경 사항
   - Memory buffer 오류 수정
   
   ## 테스트
   - [x] pytest tests/agents/ 통과
   - [x] Celery worker 정상 작동 확인
   
   ## 체크리스트
   - [x] 코드 린트 (black, isort)
   - [x] 타입 힌트 추가
   - [x] 문서 업데이트
   ```

3. **질문/이슈**:
   - 설계 관련: 설계자 에이전트에게 문의
   - 코드 리뷰: 검토자 에이전트에게 요청

---

**설계자 에이전트**  
2026-02-12
