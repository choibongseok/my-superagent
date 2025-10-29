# 🔗 LangChain Integration Guide

> **AgentHQ에서 LangChain을 활용하는 완전 가이드**

---

## 목차
1. [왜 LangChain인가?](#왜-langchain인가)
2. [핵심 개념](#핵심-개념)
3. [Agent 아키텍처](#agent-아키텍처)
4. [구현 패턴](#구현-패턴)
5. [Best Practices](#best-practices)

---

## 왜 LangChain인가?

### 문제점 (Before LangChain)
```python
# 직접 OpenAI SDK 사용 - 유지보수 어려움
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": prompt},
    ]
)
result = response.choices[0].message.content

# 문제점:
# - Tool 통합 어려움
# - Memory 관리 복잡
# - 에러 처리 반복
# - 재사용성 낮음
# - 모니터링 부족
```

### 해결책 (After LangChain)
```python
# LangChain으로 구조화 - 확장 가능, 유지보수 쉬움
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory

# LLM 초기화
llm = ChatOpenAI(model="gpt-4", callbacks=[langfuse_handler])

# Tools 정의
tools = [web_search_tool, google_docs_tool]

# Agent 생성
agent = create_openai_functions_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, memory=memory)

# 실행
result = await executor.ainvoke({"input": prompt})

# 장점:
# ✅ Tool 통합 간편
# ✅ Memory 자동 관리
# ✅ 에러 처리 내장
# ✅ 재사용 가능
# ✅ 모니터링 통합 (LangFuse)
```

---

## 핵심 개념

### 1. Chains
> **순차적인 LLM 호출 파이프라인**

```python
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

# Simple Chain
prompt = PromptTemplate.from_template("Translate {text} to {language}")
chain = LLMChain(llm=llm, prompt=prompt)

result = chain.run(text="Hello", language="Korean")
# Output: "안녕하세요"
```

### 2. Agents
> **도구를 사용하여 자율적으로 작업을 수행하는 시스템**

```python
from langchain.agents import create_openai_functions_agent

# Agent = LLM + Tools + Prompt + Memory
agent = create_openai_functions_agent(
    llm=llm,
    tools=[search_tool, calculator_tool],
    prompt=agent_prompt,
)

executor = AgentExecutor(agent=agent, tools=tools, memory=memory)
```

**Agent 작동 방식**:
```
1. User Input → Agent
2. Agent → LLM: "어떤 tool을 사용할지 결정"
3. LLM → Agent: "web_search 사용"
4. Agent → Tool: web_search("query")
5. Tool → Agent: search results
6. Agent → LLM: "결과를 종합하여 답변 생성"
7. LLM → Agent: Final answer
8. Agent → User: 답변 반환
```

### 3. Tools
> **Agent가 사용할 수 있는 기능 단위**

```python
from langchain.tools import Tool

def search_web(query: str) -> str:
    """웹 검색을 수행합니다."""
    # 실제 검색 로직
    return "검색 결과..."

# Tool 정의
search_tool = Tool(
    name="web_search",
    func=search_web,
    description="웹에서 정보를 검색할 때 사용합니다. 입력: 검색어(str)",
)
```

### 4. Memory
> **대화 컨텍스트 유지**

```python
from langchain.memory import ConversationBufferMemory

# 대화 히스토리 저장
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
)

# Agent에 연결
executor = AgentExecutor(agent=agent, tools=tools, memory=memory)

# 첫 번째 대화
await executor.ainvoke({"input": "내 이름은 John이야"})

# 두 번째 대화 - 이전 대화 기억
result = await executor.ainvoke({"input": "내 이름이 뭐였지?"})
# Output: "당신의 이름은 John입니다."
```

---

## Agent 아키텍처

### AgentHQ Agent 계층 구조

```
┌─────────────────────────────────────────┐
│          BaseAgent (추상 클래스)          │
├─────────────────────────────────────────┤
│ • LLM Provider 추상화                    │
│ • Memory 관리                            │
│ • LangFuse 통합                          │
│ • Error Handling                         │
│ • Retry Logic                            │
└──────────────┬──────────────────────────┘
               │
       ┌───────┼───────┬───────┬──────────┐
       ▼       ▼       ▼       ▼          ▼
┌───────────┐ ┌────┐ ┌──────┐ ┌─────────┐
│ Research  │ │Docs│ │Sheets│ │ Slides  │
│  Agent    │ │Agnt│ │Agent │ │ Agent   │
└───────────┘ └────┘ └──────┘ └─────────┘

각 Agent:
  - 특화된 Tools
  - 특화된 Prompts
  - 특화된 Workflows
```

### BaseAgent 구조

```python
class BaseAgent(ABC):
    """모든 Agent의 기반 클래스"""

    def __init__(self, user_id, session_id, llm_provider, ...):
        self.llm = self._create_llm(...)          # LLM 초기화
        self.memory = ConversationBufferMemory()   # Memory 초기화
        self.langfuse_handler = get_handler(...)   # 모니터링
        self.tools = []                            # Tools (하위 클래스에서 정의)
        self.agent_executor = None                 # Executor

    @abstractmethod
    def _create_tools(self) -> List[Tool]:
        """하위 클래스에서 구현"""
        pass

    @abstractmethod
    def _create_prompt(self) -> ChatPromptTemplate:
        """하위 클래스에서 구현"""
        pass

    async def run(self, prompt: str) -> dict:
        """Agent 실행"""
        result = await self.agent_executor.ainvoke(...)
        return result
```

---

## 구현 패턴

### Pattern 1: Research Agent

```python
class ResearchAgent(BaseAgent):
    """웹 리서치 전문 Agent"""

    def _create_tools(self) -> List[Tool]:
        return [
            Tool(
                name="web_search",
                func=DuckDuckGoSearchRun().run,
                description="웹 검색 도구. 최신 정보를 찾을 때 사용.",
            ),
            Tool(
                name="scrape_website",
                func=self._scrape_website,
                description="웹페이지 내용을 추출. URL을 입력받음.",
            ),
        ]

    def _create_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", """당신은 전문 리서처입니다.

책임:
1. 웹에서 정확하고 최신 정보 검색
2. 여러 소스의 정보를 분석 및 종합
3. 모든 주장에 대한 출처 제공

출력 형식:
- 핵심 발견사항 (불렛 포인트)
- 상세 분석
- 출처 인용 (번호 매긴 목록 + URL)
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
```

### Pattern 2: Google Docs Agent

```python
class DocsAgent(BaseAgent):
    """Google Docs 생성 전문 Agent"""

    def _create_tools(self) -> List[Tool]:
        return [
            Tool(
                name="create_document",
                func=self._create_document,
                description="새 Google Docs 생성. 제목과 내용을 입력받음.",
            ),
            Tool(
                name="add_heading",
                func=self._add_heading,
                description="문서에 제목 추가. 레벨(1-3)과 텍스트를 입력받음.",
            ),
            Tool(
                name="add_paragraph",
                func=self._add_paragraph,
                description="문서에 단락 추가. 텍스트를 입력받음.",
            ),
            Tool(
                name="add_table",
                func=self._add_table,
                description="문서에 표 추가. 행/열 데이터를 입력받음.",
            ),
        ]

    def _create_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", """당신은 전문 문서 작성 Agent입니다.

작업 순서:
1. create_document로 새 문서 생성
2. add_heading으로 제목 구조 생성
3. add_paragraph로 내용 작성
4. add_table로 표 추가 (필요시)

스타일 가이드:
- 제목: Heading 1-3 사용
- 본문: 명확하고 간결하게
- 표: 데이터 시각화에 활용
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
```

### Pattern 3: Multi-Agent Collaboration

```python
async def create_research_report(topic: str, user_id: str):
    """여러 Agent를 협업시켜 리포트 생성"""

    # 1. Research Agent: 정보 수집
    research_agent = ResearchAgent(user_id=user_id)
    research_result = await research_agent.run(
        prompt=f"{topic}에 대한 최신 정보 조사"
    )

    # 2. Docs Agent: 문서 작성
    docs_agent = DocsAgent(user_id=user_id)
    doc_result = await docs_agent.run(
        prompt=f"다음 리서치 결과로 보고서 작성: {research_result['output']}",
        context={"research_data": research_result},
    )

    # 3. Sheets Agent: 데이터 시각화 (Optional)
    if has_numeric_data(research_result):
        sheets_agent = SheetsAgent(user_id=user_id)
        await sheets_agent.run(
            prompt="리서치 데이터를 차트로 시각화",
            context={"data": extract_data(research_result)},
        )

    return {
        "document_url": doc_result.get("document_url"),
        "research_sources": research_result.get("sources"),
    }
```

---

## Best Practices

### 1. Prompt Engineering

**❌ 나쁜 예**:
```python
prompt = "리서치해줘"
```

**✅ 좋은 예**:
```python
prompt = """당신은 전문 리서처입니다.

작업: {task_description}

요구사항:
- 최소 3개 이상의 신뢰할 수 있는 출처 사용
- 2024년 이후 정보 우선
- 각 주장에 대한 출처 명시

출력 형식:
1. 요약 (3-5 문장)
2. 핵심 발견사항 (불렛 포인트)
3. 상세 분석
4. 출처 목록

제약사항:
- 의견과 사실 명확히 구분
- 정보 부족 시 명시적 언급
"""
```

### 2. Tool Design

**원칙**:
- **단일 책임**: 각 Tool은 하나의 명확한 기능
- **명확한 설명**: Tool description은 구체적으로
- **타입 힌팅**: 입출력 타입 명시
- **에러 처리**: 예외 상황 처리

**예시**:
```python
from typing import Optional

def search_web(
    query: str,
    max_results: int = 5,
    language: str = "en",
) -> Optional[str]:
    """
    웹 검색을 수행합니다.

    Args:
        query: 검색어
        max_results: 최대 결과 수 (기본: 5)
        language: 언어 코드 (기본: "en")

    Returns:
        검색 결과 문자열 (JSON 형식) 또는 None

    Raises:
        ValueError: query가 비어있을 때
        APIError: 검색 API 오류 시
    """
    if not query:
        raise ValueError("검색어는 비어있을 수 없습니다")

    try:
        results = search_api.search(query, max_results, language)
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return None
```

### 3. Memory Management

**전략**:
- **ConversationBufferMemory**: 짧은 대화 (<10턴)
- **ConversationSummaryMemory**: 긴 대화 (요약 사용)
- **VectorStoreMemory**: 관련 대화 검색 (시맨틱 서치)

```python
# 짧은 대화
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    max_token_limit=2000,  # 토큰 제한
)

# 긴 대화 (요약)
from langchain.memory import ConversationSummaryMemory

memory = ConversationSummaryMemory(
    llm=llm,
    memory_key="chat_history",
    return_messages=True,
)

# 시맨틱 검색
from langchain.memory import VectorStoreRetrieverMemory
from langchain.vectorstores import PGVector

vectorstore = PGVector(...)
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

memory = VectorStoreRetrieverMemory(
    retriever=retriever,
    memory_key="chat_history",
)
```

### 4. Error Handling

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class RobustAgent(BaseAgent):
    """에러에 강한 Agent"""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def run(self, prompt: str) -> dict:
        """Retry logic이 적용된 실행"""
        try:
            result = await self.agent_executor.ainvoke(
                {"input": prompt},
                config={
                    "callbacks": [self.langfuse_handler],
                    "max_execution_time": 300,  # 5분 타임아웃
                },
            )

            return {
                "output": result.get("output"),
                "success": True,
            }

        except TimeoutError as e:
            logger.error(f"Agent timeout: {e}")
            return {
                "output": None,
                "error": "작업 시간 초과",
                "success": False,
            }

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            return {
                "output": None,
                "error": str(e),
                "success": False,
            }

        finally:
            # LangFuse에 로그 전송
            self.langfuse_handler.flush()
```

### 5. Performance Optimization

```python
# Streaming 응답 (사용자 경험 개선)
async def run_with_streaming(self, prompt: str):
    """스트리밍 응답으로 실행"""
    async for chunk in self.agent_executor.astream(
        {"input": prompt},
        config={"callbacks": [self.langfuse_handler]},
    ):
        if "output" in chunk:
            yield chunk["output"]

# 병렬 Tool 실행
from langchain.agents import ParallelToolsAgent

agent = ParallelToolsAgent(
    llm=llm,
    tools=tools,
    max_parallel_tools=3,  # 최대 3개 병렬 실행
)

# Caching (반복 호출 최적화)
from langchain.cache import RedisCache
import langchain

langchain.llm_cache = RedisCache(redis_url="redis://localhost:6379")
```

---

## 참고 자료

### 공식 문서
- [LangChain Docs](https://python.langchain.com/)
- [LangChain Agents](https://python.langchain.com/docs/modules/agents/)
- [LangChain Tools](https://python.langchain.com/docs/modules/agents/tools/)
- [LangChain Memory](https://python.langchain.com/docs/modules/memory/)

### 예제 코드
- [LangChain Examples](https://github.com/langchain-ai/langchain/tree/master/docs/docs/modules/agents)
- [Agent Templates](https://github.com/langchain-ai/langchain/tree/master/templates)

### 커뮤니티
- [LangChain Discord](https://discord.gg/langchain)
- [LangChain Twitter](https://twitter.com/LangChainAI)

---

**Last Updated**: 2024-10-29
**Version**: 1.0
