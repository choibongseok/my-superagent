# 🚀 Phase 0: Foundation Enhancement - 실행 가이드

> **목표**: LangChain/LangFuse 통합으로 세계 최고 수준 기반 구축
> **기간**: 2주 (Week 1-2)
> **우선순위**: P0 (CRITICAL)

---

## 📋 목차
1. [환경 설정](#환경-설정)
2. [Week 1: LangChain & LangFuse 통합](#week-1-langchain--langfuse-통합)
3. [Week 2: Prompt Management & Testing](#week-2-prompt-management--testing)
4. [검증 체크리스트](#검증-체크리스트)

---

## 환경 설정

### 1. 의존성 업데이트

```bash
cd backend

# requirements.txt에 추가
cat >> requirements.txt << 'EOF'

# LangChain Core
langchain==0.1.0
langchain-core==0.1.0
langchain-community==0.0.10

# LangChain Providers
langchain-openai==0.0.2
langchain-anthropic==0.1.0

# LangFuse
langfuse==2.6.0
langfuse-langchain==2.6.0

# Additional Tools
duckduckgo-search==4.1.0
EOF

# 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
# .env에 추가
cat >> .env << 'EOF'

# LangChain
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=agenthq

# LangFuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted URL

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
EOF
```

### 3. LangFuse 설정

#### Option A: Cloud (권장 - 빠른 시작)
```bash
# 1. https://cloud.langfuse.com 회원가입
# 2. 새 프로젝트 생성: "AgentHQ"
# 3. Settings > API Keys에서 키 복사
# 4. .env에 추가
```

#### Option B: Self-Hosted (엔터프라이즈)
```bash
# docker-compose.yml에 추가
cat >> docker-compose.yml << 'EOF'
  langfuse-server:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langfuse
      - NEXTAUTH_SECRET=your-secret-here
      - NEXTAUTH_URL=http://localhost:3000
    depends_on:
      - postgres
EOF

docker-compose up -d langfuse-server
```

---

## Week 1: LangChain & LangFuse 통합

### Day 1-2: BaseAgent 구조 구축

#### 1. Agent 디렉토리 구조 생성

```bash
mkdir -p backend/app/agents/tools
touch backend/app/agents/__init__.py
touch backend/app/agents/base.py
touch backend/app/agents/research_agent.py
touch backend/app/agents/docs_agent.py
touch backend/app/agents/sheets_agent.py
touch backend/app/agents/slides_agent.py
touch backend/app/agents/memory_manager.py
touch backend/app/agents/tools/__init__.py
touch backend/app/agents/tools/web_search.py
touch backend/app/agents/tools/google_apis.py
```

#### 2. LangFuse Client 초기화

```bash
# backend/app/core/langfuse.py 생성
cat > backend/app/core/langfuse.py << 'EOF'
"""LangFuse integration for LLM observability."""

import os
from functools import wraps
from typing import Any, Callable

from langfuse import Langfuse
from langfuse.callback import CallbackHandler

# Initialize LangFuse client
langfuse_client = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


def get_langfuse_handler(
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CallbackHandler:
    """
    Create LangFuse callback handler for tracing.

    Args:
        user_id: User identifier
        session_id: Session identifier
        metadata: Additional metadata

    Returns:
        CallbackHandler instance
    """
    return CallbackHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )


def trace_llm(
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """
    Decorator for tracing LLM calls with LangFuse.

    Usage:
        @trace_llm(name="research_agent", metadata={"version": "1.0"})
        def my_agent_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            trace_name = name or func.__name__
            trace = langfuse_client.trace(
                name=trace_name,
                metadata=metadata,
            )

            try:
                result = await func(*args, **kwargs, trace_id=trace.id)
                trace.update(output=result)
                return result
            except Exception as e:
                trace.update(
                    output=None,
                    status_message=str(e),
                    level="ERROR",
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            trace_name = name or func.__name__
            trace = langfuse_client.trace(
                name=trace_name,
                metadata=metadata,
            )

            try:
                result = func(*args, **kwargs, trace_id=trace.id)
                trace.update(output=result)
                return result
            except Exception as e:
                trace.update(
                    output=None,
                    status_message=str(e),
                    level="ERROR",
                )
                raise

        # Detect if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


__all__ = [
    "langfuse_client",
    "get_langfuse_handler",
    "trace_llm",
]
EOF
```

#### 3. BaseAgent 추상 클래스 구현

```bash
# backend/app/agents/base.py 생성
cat > backend/app/agents/base.py << 'EOF'
"""Base agent class with LangChain and LangFuse integration."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.core.langfuse import get_langfuse_handler, trace_llm


class BaseAgent(ABC):
    """
    Base class for all agents with LangChain and LangFuse integration.

    Features:
        - LLM provider abstraction (OpenAI, Anthropic)
        - LangFuse tracing and monitoring
        - Memory management
        - Tool integration
        - Error handling and retry logic
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        llm_provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        memory: Optional[ConversationBufferMemory] = None,
    ):
        """
        Initialize base agent.

        Args:
            user_id: User identifier for tracking
            session_id: Session identifier for grouping
            llm_provider: "openai" or "anthropic"
            model: Model name
            temperature: LLM temperature (0-1)
            max_tokens: Max output tokens
            memory: Optional memory instance
        """
        self.user_id = user_id
        self.session_id = session_id or f"session_{user_id}"

        # Initialize LLM
        self.llm = self._create_llm(llm_provider, model, temperature, max_tokens)

        # Initialize memory
        self.memory = memory or ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
        )

        # LangFuse callback handler
        self.langfuse_handler = get_langfuse_handler(
            user_id=self.user_id,
            session_id=self.session_id,
            metadata=self._get_metadata(),
        )

        # Tools will be set by subclasses
        self.tools: List[Any] = []

        # Agent executor (initialized in subclasses)
        self.agent_executor: Optional[AgentExecutor] = None

    def _create_llm(
        self,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        """Create LLM instance based on provider."""
        if provider == "openai":
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=[self.langfuse_handler] if hasattr(self, 'langfuse_handler') else None,
            )
        elif provider == "anthropic":
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=[self.langfuse_handler] if hasattr(self, 'langfuse_handler') else None,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @abstractmethod
    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata for LangFuse tracking."""
        pass

    @abstractmethod
    def _create_tools(self) -> List[Any]:
        """Create agent-specific tools."""
        pass

    @abstractmethod
    def _create_prompt(self) -> ChatPromptTemplate:
        """Create agent-specific prompt template."""
        pass

    def initialize_agent(self):
        """Initialize agent with tools and prompt."""
        # Create tools
        self.tools = self._create_tools()

        # Create prompt
        prompt = self._create_prompt()

        # Create agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )

        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=settings.DEBUG,
            max_iterations=10,
            max_execution_time=300,  # 5 minutes
            callbacks=[self.langfuse_handler],
        )

    @trace_llm(name="agent_run")
    async def run(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run agent with prompt.

        Args:
            prompt: User prompt
            context: Additional context
            trace_id: LangFuse trace ID (injected by decorator)

        Returns:
            Agent output dictionary
        """
        if not self.agent_executor:
            self.initialize_agent()

        try:
            # Prepare input
            agent_input = {
                "input": prompt,
                **(context or {}),
            }

            # Run agent
            result = await self.agent_executor.ainvoke(
                agent_input,
                config={
                    "callbacks": [self.langfuse_handler],
                    "metadata": {
                        "trace_id": trace_id,
                        "user_id": self.user_id,
                        "session_id": self.session_id,
                    },
                },
            )

            return {
                "output": result.get("output"),
                "intermediate_steps": result.get("intermediate_steps", []),
                "success": True,
            }

        except Exception as e:
            # Log error to LangFuse
            self.langfuse_handler.flush()

            return {
                "output": None,
                "error": str(e),
                "success": False,
            }

    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear()


__all__ = ["BaseAgent"]
EOF
```

### Day 3-4: Research Agent 구현

```bash
# backend/app/agents/research_agent.py 생성
cat > backend/app/agents/research_agent.py << 'EOF'
"""Research Agent for web search and analysis."""

from typing import Any, Dict, List

from langchain.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    """
    Agent for web research and information gathering.

    Features:
        - Web search (DuckDuckGo)
        - Content extraction
        - Source citation
        - Information synthesis
    """

    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata."""
        return {
            "agent_type": "research",
            "version": "1.0",
            "capabilities": ["web_search", "citation", "synthesis"],
        }

    def _create_tools(self) -> List[Tool]:
        """Create research tools."""
        # DuckDuckGo search tool
        search = DuckDuckGoSearchRun()

        tools = [
            Tool(
                name="web_search",
                func=search.run,
                description=(
                    "Useful for searching the web for current information. "
                    "Input should be a search query string. "
                    "Returns search results with titles and snippets."
                ),
            ),
        ]

        return tools

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create research agent prompt."""
        system_message = """You are a professional research agent.

Your responsibilities:
1. Search the web for accurate, up-to-date information
2. Analyze and synthesize information from multiple sources
3. Provide citations for all claims
4. Present information in a clear, structured format

Guidelines:
- Always cite your sources with URLs
- Prioritize recent and authoritative sources
- Cross-reference information when possible
- Clearly distinguish facts from opinions
- Be transparent about information gaps

Output format:
- Key findings (bullet points)
- Detailed analysis
- Source citations (numbered list with URLs)
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        return prompt


__all__ = ["ResearchAgent"]
EOF
```

### Day 5: 첫 테스트 및 검증

```bash
# backend/tests/test_agents.py 생성
mkdir -p backend/tests
cat > backend/tests/test_research_agent.py << 'EOF'
"""Tests for Research Agent."""

import pytest
from app.agents.research_agent import ResearchAgent


@pytest.mark.asyncio
async def test_research_agent_creation():
    """Test research agent initialization."""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session",
    )

    assert agent.user_id == "test_user"
    assert agent.session_id == "test_session"
    assert agent.llm is not None


@pytest.mark.asyncio
async def test_research_agent_run():
    """Test research agent execution."""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session",
    )

    result = await agent.run(
        prompt="What are the latest trends in AI in 2024?",
    )

    assert result["success"] is True
    assert result["output"] is not None
    assert len(result["output"]) > 0


@pytest.mark.asyncio
async def test_research_agent_with_context():
    """Test research agent with additional context."""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session",
    )

    result = await agent.run(
        prompt="Summarize key points about LangChain",
        context={
            "focus_areas": ["architecture", "use_cases"],
        },
    )

    assert result["success"] is True
    assert "LangChain" in result["output"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
EOF

# 테스트 실행
cd backend
pytest tests/test_research_agent.py -v
```

### Day 6-7: 나머지 Agent Stub 생성

```bash
# Google Docs Agent stub
cat > backend/app/agents/docs_agent.py << 'EOF'
"""Google Docs Agent for document generation."""

from typing import Any, Dict, List

from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent


class DocsAgent(BaseAgent):
    """
    Agent for Google Docs generation.

    TODO: Implement in Phase 1
    """

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "docs",
            "version": "0.1",
            "status": "stub",
        }

    def _create_tools(self) -> List[Tool]:
        # TODO: Implement Google Docs API tools
        return []

    def _create_prompt(self) -> ChatPromptTemplate:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a document generation agent. (TODO: Implement)"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["DocsAgent"]
EOF

# 같은 방식으로 sheets_agent.py, slides_agent.py 생성
# (구조는 동일, 구현은 Phase 1에서 완성)
```

---

## Week 2: Prompt Management & Testing

### Day 8-9: Prompt Management System

```bash
# backend/app/prompts/ 디렉토리 생성
mkdir -p backend/app/prompts/templates
touch backend/app/prompts/__init__.py

# Prompt Registry 구현
cat > backend/app/prompts/registry.py << 'EOF'
"""Prompt Registry for version management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PromptVersion(BaseModel):
    """Prompt version model."""
    version: str
    template: str
    variables: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    performance_score: Optional[float] = None


class PromptRegistry:
    """
    Registry for managing prompt templates and versions.

    Features:
        - Version management
        - A/B testing support
        - Performance tracking (via LangFuse)
        - Rollback capability
    """

    def __init__(self, storage_path: str = "prompts/templates"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[PromptVersion]] = {}

    def register(
        self,
        name: str,
        template: str,
        variables: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> PromptVersion:
        """Register new prompt or version."""
        # Auto-generate version if not provided
        if version is None:
            existing = self.list_versions(name)
            version = f"v{len(existing) + 1}"

        prompt_version = PromptVersion(
            version=version,
            template=template,
            variables=variables,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

        # Save to file
        self._save_version(name, prompt_version)

        # Update cache
        if name not in self._cache:
            self._cache[name] = []
        self._cache[name].append(prompt_version)

        return prompt_version

    def get(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[PromptVersion]:
        """Get prompt by name and version."""
        versions = self.list_versions(name)

        if not versions:
            return None

        if version is None:
            # Return latest version
            return versions[-1]

        # Find specific version
        for v in versions:
            if v.version == version:
                return v

        return None

    def list_versions(self, name: str) -> List[PromptVersion]:
        """List all versions of a prompt."""
        if name in self._cache:
            return self._cache[name]

        # Load from file
        file_path = self.storage_path / f"{name}.json"
        if not file_path.exists():
            return []

        with open(file_path, "r") as f:
            data = json.load(f)

        versions = [PromptVersion(**v) for v in data]
        self._cache[name] = versions

        return versions

    def _save_version(self, name: str, version: PromptVersion):
        """Save prompt version to file."""
        versions = self.list_versions(name)
        versions.append(version)

        file_path = self.storage_path / f"{name}.json"
        with open(file_path, "w") as f:
            json.dump(
                [v.dict() for v in versions],
                f,
                indent=2,
                default=str,
            )


# Global registry instance
prompt_registry = PromptRegistry()


__all__ = ["PromptRegistry", "PromptVersion", "prompt_registry"]
EOF

# Research Agent 프롬프트 등록
cat > backend/app/prompts/templates/research.py << 'EOF'
"""Research agent prompt templates."""

from app.prompts.registry import prompt_registry

# Register default research prompt
prompt_registry.register(
    name="research_agent",
    template="""You are a professional research agent.

Your responsibilities:
1. Search the web for accurate, up-to-date information
2. Analyze and synthesize information from multiple sources
3. Provide citations for all claims
4. Present information in a clear, structured format

Topic: {topic}
Focus areas: {focus_areas}

Guidelines:
- Always cite your sources with URLs
- Prioritize recent and authoritative sources
- Cross-reference information when possible
- Clearly distinguish facts from opinions

Output format:
- Key findings (bullet points)
- Detailed analysis
- Source citations
""",
    variables=["topic", "focus_areas"],
    metadata={
        "agent": "research",
        "purpose": "web_research",
        "language": "en",
    },
    version="v1",
)
EOF
```

### Day 10-12: Comprehensive Testing

```bash
# pytest.ini 설정
cat > backend/pytest.ini << 'EOF'
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
asyncio_mode = auto
EOF

# 통합 테스트 작성
cat > backend/tests/test_integration.py << 'EOF'
"""Integration tests for agent system."""

import pytest
from app.agents.research_agent import ResearchAgent
from app.prompts.registry import prompt_registry


@pytest.mark.asyncio
async def test_research_agent_with_prompt_registry():
    """Test research agent with prompt from registry."""
    # Get prompt from registry
    prompt_version = prompt_registry.get("research_agent", version="v1")
    assert prompt_version is not None

    # Create agent
    agent = ResearchAgent(
        user_id="test_user",
        session_id="integration_test",
    )

    # Run agent
    result = await agent.run(
        prompt="Research latest AI trends",
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_langfuse_tracing():
    """Test LangFuse tracing integration."""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="langfuse_test",
    )

    result = await agent.run(
        prompt="Test LangFuse tracing",
    )

    # Verify result
    assert result["success"] is True

    # Note: Check LangFuse dashboard manually for traces


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
EOF

# 테스트 실행
pytest backend/tests/ -v --cov=backend/app --cov-report=html
```

### Day 13-14: Documentation & CI/CD

```bash
# GitHub Actions 워크플로우 생성
mkdir -p .github/workflows
cat > .github/workflows/test.yml << 'EOF'
name: Test

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        cd backend
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov

    - name: Run tests
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_db
        REDIS_URL: redis://localhost:6379/0
        OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
        LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
      run: |
        cd backend
        pytest tests/ -v --cov=app --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        files: ./backend/coverage.xml
EOF
```

---

## 검증 체크리스트

### Week 1 완료 기준

#### LangChain 통합
- [ ] LangChain 설치 완료
- [ ] BaseAgent 클래스 구현 완료
- [ ] ResearchAgent 구현 및 테스트 통과
- [ ] Agent가 웹 검색 수행 가능
- [ ] Agent 실행 결과 정상 반환

#### LangFuse 통합
- [ ] LangFuse 계정 생성 또는 Self-Hosted 설정
- [ ] LangFuse Callback Handler 통합
- [ ] 대시보드에서 Trace 확인 가능
- [ ] LLM 호출 비용 추적 가능
- [ ] 에러 추적 정상 작동

### Week 2 완료 기준

#### Prompt Management
- [ ] PromptRegistry 구현 완료
- [ ] 프롬프트 등록/조회 기능 작동
- [ ] 버전 관리 기능 작동
- [ ] Agent에서 Registry 사용 가능

#### Testing
- [ ] 단위 테스트 작성 완료 (80%+ 커버리지)
- [ ] 통합 테스트 작성 완료
- [ ] pytest 실행 성공
- [ ] Coverage 리포트 생성

#### CI/CD
- [ ] GitHub Actions 워크플로우 설정
- [ ] 자동 테스트 실행 성공
- [ ] Coverage 업로드 성공

#### Documentation
- [ ] 코드 주석 작성 완료
- [ ] README 업데이트 완료
- [ ] API 문서 생성 완료

---

## 다음 단계 (Phase 1)

Phase 0 완료 후 Phase 1으로 진행:

1. **Research Agent 완전 구현**
   - Playwright 통합
   - Content Extraction
   - Source Citation

2. **Google Docs Agent 구현**
   - Google Docs API 통합
   - Document 생성 기능
   - 스타일 적용

3. **Google Sheets Agent 구현**
   - Google Sheets API 통합
   - 데이터 구조화
   - 차트 생성

4. **Google Slides Agent 구현**
   - Google Slides API 통합
   - 슬라이드 레이아웃
   - 콘텐츠 배치

---

## 참고 자료

### LangChain
- [Quick Start Guide](https://python.langchain.com/docs/get_started/quickstart)
- [Agent Documentation](https://python.langchain.com/docs/modules/agents/)
- [Custom Tools](https://python.langchain.com/docs/modules/agents/tools/custom_tools)

### LangFuse
- [Getting Started](https://langfuse.com/docs/get-started)
- [Python SDK](https://langfuse.com/docs/sdk/python)
- [LangChain Integration](https://langfuse.com/docs/integrations/langchain/tracing)

### Testing
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Last Updated**: 2024-10-29
**Phase**: 0
**Status**: Ready to Start
