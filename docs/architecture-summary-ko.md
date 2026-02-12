# 🎯 AgentHQ 아키텍처 분석 요약 (한국어)

**작성일**: 2026-02-12  
**작성자**: 설계자 에이전트

---

## 📊 핵심 발견 사항

### 1. 전체 구조
- **Backend**: FastAPI + LangChain + Celery (Python)
- **Desktop**: Tauri + React (Rust + TypeScript)
- **Mobile**: Flutter (Dart)
- **Data**: PostgreSQL (PGVector) + Redis

### 2. 주요 문제점

#### 🔴 Critical (즉시 수정 필요)
1. **Memory buffer 오류**: `self.memory.buffer` AttributeError
   - 원인: LangChain Memory 객체 접근 방식 오류
   - 해결: `.buffer` → `.langchain_memory` 또는 `.memory`

2. **Alembic 마이그레이션 오류**: UUID import 누락
   - 파일: `c4d39e6ece1f_add_chat_and_message_models.py`
   - 해결: `import uuid` 추가

3. **Celery async 미처리**: Agent의 비동기 함수 호출 오류
   - 원인: `await` 없이 async 함수 호출
   - 해결: `asyncio.run_until_complete()` 사용

#### 🟡 High Priority (1주 내)
4. **Sheets/Slides Agent 미구현**: 핵심 기능 TODO 상태
5. **Google Credentials 전달 오류**: Agent에서 OAuth 토큰 누락
6. **Mobile OAuth 미구현**: 더미 로그인만 존재

#### 🟢 Medium Priority (2주 내)
7. **MemoryManager 미사용**: Phase 2 구현이 실제로 연결 안 됨
8. **Citation Tracker 미연결**: 인용 추적 시스템 미활용

---

## 🏗️ 재설계 제안

### 1. Memory System (3-Layer 아키텍처)

```
Layer 1 (Agent): ConversationBufferMemory (현재 대화만)
              ↓
Layer 2 (Session): ConversationMemory (세션 히스토리)
              ↓
Layer 3 (Long-term): VectorStoreMemory (임베딩 검색)
```

### 2. Agent Communication (Event-Driven)

```python
EventBus를 통한 Agent 간 통신
- 낮은 결합도
- 비동기 워크플로우 자연스럽게 처리
- 디버깅 용이
```

### 3. Database Optimization

**추가 인덱스:**
- `tasks.user_id`, `tasks.status`, `tasks.created_at`
- `messages.created_at`, 복합 인덱스 추가
- JSONB GIN 인덱스

**새 테이블:**
- `task_executions` (재시도 히스토리)
- `agent_sessions` (멀티 에이전트 추적)
- `conversation_memories`, `vector_memories` (Memory 영속성)

---

## 📅 구현 우선순위

### Week 1: Critical Fixes + Core Features
- **Day 1**: Phase 0 (Memory buffer, Alembic, Celery 수정)
- **Day 2-4**: Phase 1 (Sheets/Slides Agent 구현)
- **Day 5**: Phase 2 시작 (Memory 통합)

### Week 2: Integration & Optimization
- **Day 1-2**: Phase 2 완료 (MemoryManager)
- **Day 3-4**: Phase 3 (Agent Communication)
- **Day 5**: Phase 4 (DB Optimization)

**총 예상 시간**: 2주 (10일)

---

## 🚀 다음 단계 (개발자 에이전트)

### 즉시 착수 작업

1. **Memory buffer 수정** (2시간)
   ```python
   # backend/app/memory/conversation.py
   @property
   def langchain_memory(self):  # buffer → langchain_memory
       return self.memory
   
   # backend/app/agents/base.py
   memory=self.memory.langchain_memory  # 수정
   ```

2. **Alembic UUID import** (1시간)
   ```python
   # backend/alembic/versions/c4d39e6ece1f_*.py
   import uuid  # 추가
   ```

3. **Celery async 처리** (3시간)
   ```python
   # backend/app/agents/celery_app.py
   import asyncio
   loop = asyncio.get_event_loop()
   result = loop.run_until_complete(agent.run(prompt))
   ```

### 검증 방법

```bash
# 1. 단위 테스트
cd backend
pytest tests/agents/ -v
pytest tests/memory/ -v

# 2. Agent 실행 테스트
python -c "
from app.agents.research_agent import ResearchAgent
import asyncio
agent = ResearchAgent(user_id='test', session_id='test')
asyncio.run(agent.run('Test'))
"

# 3. Celery worker 테스트
celery -A app.agents.celery_app worker --loglevel=info
```

---

## ✅ 성공 기준

**2주 후:**
- [ ] 모든 Agent 정상 작동
- [ ] Memory 시스템 완전 통합
- [ ] Multi-agent 워크플로우 안정화
- [ ] 데이터베이스 인덱스 최적화 완료
- [ ] Mobile OAuth 구현 완료

**4주 후:**
- [ ] Production-ready 상태
- [ ] 90%+ 테스트 커버리지
- [ ] CI/CD 자동화
- [ ] 모니터링 대시보드

---

## 📎 관련 문서

- **상세 분석**: `docs/architecture-review.md` (43KB, 완전 문서)
- **기존 계획**: `docs/PHASE_PLAN.md`
- **구현 가이드**: `docs/PHASE_*_IMPLEMENTATION.md`

---

**설계자 에이전트**  
다음: 개발자 에이전트에게 전달
