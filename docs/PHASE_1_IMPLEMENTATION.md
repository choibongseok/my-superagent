# Phase 1 Implementation Guide: Core Agent Implementation

> **목표**: 4가지 핵심 Agent 완전 구현 및 Google Workspace 통합
> **기간**: 2-4주
> **우선순위**: P0 (Critical Path)

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Implementation](#implementation)
5. [Testing](#testing)
6. [Deployment](#deployment)
7. [Success Criteria](#success-criteria)

---

## Overview

Phase 1은 AgentHQ의 핵심 기능인 4가지 Agent를 구현합니다:
1. **Research Agent**: Web 검색 및 정보 수집
2. **Docs Agent**: Google Docs 문서 자동 생성
3. **Sheets Agent**: Google Sheets 데이터 분석 및 시각화
4. **Slides Agent**: Google Slides 프레젠테이션 생성

### Key Features
- ✅ LangChain 기반 구조화된 Agent Pipeline
- ✅ Google Workspace API 완전 통합
- ✅ 인용 출처 자동 추적 (Citation Tracking)
- ✅ 컨텍스트 기반 문서 생성
- ✅ LangFuse 모니터링 통합

---

## Prerequisites

### Required Knowledge
- LangChain Agent 아키텍처 ([LANGCHAIN_GUIDE.md](LANGCHAIN_GUIDE.md) 참고)
- Google Workspace API 사용법 ([OAUTH_SETUP.md](OAUTH_SETUP.md) 참고)
- Phase 0 완료 (LangChain/LangFuse 통합)
- Phase 2 완료 (Memory & Citation System)

### Environment Setup
```bash
# 1. Phase 0, 2 dependencies already installed
pip install -r requirements.txt

# 2. Additional dependencies for Phase 1
pip install duckduckgo-search==4.1.0
pip install google-api-python-client==2.108.0
pip install beautifulsoup4==4.12.2
pip install playwright==1.40.0

# 3. Install Playwright browsers
playwright install chromium

# 4. Verify Google OAuth credentials
ls -la backend/credentials.json
```

### Google Cloud Setup
```bash
# Enable required APIs
gcloud services enable docs.googleapis.com
gcloud services enable sheets.googleapis.com
gcloud services enable slides.googleapis.com
gcloud services enable drive.googleapis.com
```

---

## Architecture

### Agent System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestration Layer                │
├─────────────────┬───────────────┬───────────────┬───────────┤
│  Research Agent │   Docs Agent  │ Sheets Agent  │Slides Agent│
│   Web Search    │  Doc Creation │ Data Analysis │Presentation│
├─────────────────┴───────────────┴───────────────┴───────────┤
│                     LangChain Framework                      │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │   Chains   │    Tools     │   Memory    │  Callbacks   │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    External Services                         │
│  ┌──────────────┬──────────────┬───────────────┐            │
│  │ Google APIs  │  Web Search  │   LangFuse    │            │
│  └──────────────┴──────────────┴───────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure
```
backend/app/agents/
├── __init__.py
├── base.py                    # BaseAgent 추상 클래스
├── research_agent.py          # Research Agent 구현
├── docs_agent.py              # Google Docs Agent 구현
├── sheets_agent.py            # Google Sheets Agent 구현
├── slides_agent.py            # Google Slides Agent 구현
├── tools/                     # Agent Tools
│   ├── __init__.py
│   ├── web_search.py          # DuckDuckGo & Web Scraping
│   ├── google_docs.py         # Google Docs API Tools
│   ├── google_sheets.py       # Google Sheets API Tools
│   └── google_slides.py       # Google Slides API Tools
└── prompts/                   # Agent Prompts
    ├── __init__.py
    ├── research_prompts.py    # Research Agent Prompts
    ├── docs_prompts.py        # Docs Agent Prompts
    ├── sheets_prompts.py      # Sheets Agent Prompts
    └── slides_prompts.py      # Slides Agent Prompts
```

---

## Implementation

### 1. Research Agent Implementation

#### 1.1 Web Search Tool

**File**: `backend/app/agents/tools/web_search.py`

```python
from langchain.tools import Tool
from duckduckgo_search import DDGS
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

class WebSearchTool:
    """Web search and content extraction tool"""

    def __init__(self):
        self.ddg = DDGS()

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search web using DuckDuckGo

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of search results with title, url, and snippet
        """
        results = []

        try:
            # DuckDuckGo search
            search_results = self.ddg.text(query, max_results=max_results)

            for result in search_results:
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('href', ''),
                    'snippet': result.get('body', '')
                })
        except Exception as e:
            print(f"Search error: {e}")

        return results

    async def scrape_content(self, url: str) -> Optional[Dict]:
        """
        Scrape content from URL using Playwright

        Args:
            url: URL to scrape

        Returns:
            Dictionary with title and content
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Navigate with timeout
                await page.goto(url, wait_until='domcontentloaded', timeout=10000)

                # Get page content
                content = await page.content()
                await browser.close()

                # Parse with BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')

                # Extract title
                title = soup.title.string if soup.title else ''

                # Extract main content (remove script, style tags)
                for tag in soup(['script', 'style', 'nav', 'footer']):
                    tag.decompose()

                text = soup.get_text(separator='\n', strip=True)

                return {
                    'title': title,
                    'content': text[:5000],  # Limit to 5000 chars
                    'url': url
                }

        except Exception as e:
            print(f"Scraping error for {url}: {e}")
            return None

def create_search_tool() -> Tool:
    """Create LangChain search tool"""
    search_tool = WebSearchTool()

    async def search_wrapper(query: str) -> str:
        results = await search_tool.search(query)

        if not results:
            return "No results found."

        output = []
        for i, result in enumerate(results, 1):
            output.append(f"{i}. {result['title']}\n   {result['url']}\n   {result['snippet']}")

        return "\n\n".join(output)

    return Tool(
        name="web_search",
        description="Search the web for information. Input should be a search query string.",
        func=search_wrapper
    )
```

#### 1.2 Research Agent

**File**: `backend/app/agents/research_agent.py`

```python
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Dict, List, Optional
from app.agents.base import BaseAgent
from app.agents.tools.web_search import create_search_tool
from app.services.citation.tracker import CitationTracker
from app.services.citation.models import SourceType

class ResearchAgent(BaseAgent):
    """Agent for web research and information gathering"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        llm_provider: str = "openai",
        model: str = "gpt-4"
    ):
        super().__init__(user_id, session_id, llm_provider, model)

        # Initialize citation tracker
        self.citation_tracker = CitationTracker()

        # Setup tools
        self.tools = [
            create_search_tool()
        ]

        # Setup agent
        self._setup_agent()

    def _setup_agent(self):
        """Setup LangChain agent with tools"""

        # Define prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5,
            callbacks=[self.langfuse_handler]
        )

    def _get_system_prompt(self) -> str:
        """Get system prompt for research agent"""
        return """You are a professional research assistant. Your job is to:

1. Search for relevant and credible information on the web
2. Analyze and synthesize information from multiple sources
3. Provide accurate, well-cited responses
4. Track all sources for proper citation

Guidelines:
- Use multiple search queries to get comprehensive results
- Prioritize credible sources (official sites, research papers, reputable news)
- Cross-reference information when possible
- Always cite your sources
- Be objective and factual

When providing information:
- State facts clearly
- Include source URLs
- Note any conflicting information
- Distinguish between facts and opinions"""

    async def research(self, query: str) -> Dict:
        """
        Conduct research on a topic

        Args:
            query: Research query

        Returns:
            Dictionary with research results and citations
        """
        try:
            # Add user query to memory
            self.memory.add_user_message(query)

            # Execute agent
            result = await self.agent_executor.ainvoke({
                "input": query,
                "chat_history": self.memory.get_messages()
            })

            # Add AI response to memory
            self.memory.add_ai_message(result['output'])

            # Return result with citations
            return {
                'answer': result['output'],
                'citations': self.citation_tracker.get_all_sources(),
                'bibliography': self.citation_tracker.get_bibliography(style='apa')
            }

        except Exception as e:
            print(f"Research error: {e}")
            raise

    async def research_with_citation(
        self,
        query: str,
        include_urls: bool = True
    ) -> Dict:
        """
        Research with automatic citation tracking

        Args:
            query: Research query
            include_urls: Include source URLs in response

        Returns:
            Research results with tracked citations
        """
        result = await self.research(query)

        # Format response with citations
        if include_urls and result['citations']:
            result['answer'] += "\n\n## Sources\n"
            for source in result['citations']:
                result['answer'] += f"- {source.title}: {source.url}\n"

        return result
```

### 2. Google Docs Agent Implementation

#### 2.1 Google Docs Tool

**File**: `backend/app/agents/tools/google_docs.py`

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Dict, List, Optional
import markdown
from app.services.citation.models import Source

class GoogleDocsTools:
    """Tools for Google Docs API operations"""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build('docs', 'v1', credentials=credentials)

    def create_document(self, title: str) -> str:
        """
        Create a new Google Doc

        Args:
            title: Document title

        Returns:
            Document ID
        """
        try:
            doc = self.service.documents().create(body={'title': title}).execute()
            return doc.get('documentId')
        except HttpError as error:
            print(f"Error creating document: {error}")
            raise

    def insert_text(
        self,
        document_id: str,
        text: str,
        index: int = 1
    ) -> bool:
        """
        Insert text into document

        Args:
            document_id: Document ID
            text: Text to insert
            index: Insertion index (default: 1 = end)

        Returns:
            Success boolean
        """
        try:
            requests = [{
                'insertText': {
                    'location': {'index': index},
                    'text': text
                }
            }]

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            return True
        except HttpError as error:
            print(f"Error inserting text: {error}")
            return False

    def apply_heading_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        heading_level: int = 1
    ) -> bool:
        """
        Apply heading style to text range

        Args:
            document_id: Document ID
            start_index: Start index
            end_index: End index
            heading_level: Heading level (1-6)

        Returns:
            Success boolean
        """
        try:
            style_name = f'HEADING_{heading_level}'

            requests = [{
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': end_index
                    },
                    'paragraphStyle': {
                        'namedStyleType': style_name
                    },
                    'fields': 'namedStyleType'
                }
            }]

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            return True
        except HttpError as error:
            print(f"Error applying heading: {error}")
            return False

    def markdown_to_docs(
        self,
        document_id: str,
        markdown_text: str,
        citations: Optional[List[Source]] = None
    ) -> bool:
        """
        Convert markdown to Google Docs with formatting

        Args:
            document_id: Document ID
            markdown_text: Markdown text
            citations: List of citations to append

        Returns:
            Success boolean
        """
        try:
            # Convert markdown to HTML first (for structure)
            html = markdown.markdown(markdown_text)

            # For simplicity, insert as plain text first
            # In production, parse HTML and apply appropriate styles
            self.insert_text(document_id, markdown_text)

            # Append citations if provided
            if citations:
                citation_text = "\n\n## References\n"
                for i, cite in enumerate(citations, 1):
                    citation_text += f"{i}. {cite.to_citation_format('apa')}\n"

                self.insert_text(document_id, citation_text, index=1)

            return True
        except Exception as error:
            print(f"Error converting markdown: {error}")
            return False
```

#### 2.2 Docs Agent

**File**: `backend/app/agents/docs_agent.py`

```python
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool
from typing import Dict, Optional, List
from app.agents.base import BaseAgent
from app.agents.tools.google_docs import GoogleDocsTools
from app.services.citation.models import Source

class DocsAgent(BaseAgent):
    """Agent for Google Docs document generation"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        credentials,
        llm_provider: str = "openai",
        model: str = "gpt-4"
    ):
        super().__init__(user_id, session_id, llm_provider, model)

        # Initialize Google Docs tools
        self.docs_tools = GoogleDocsTools(credentials)

        # Setup agent
        self._setup_agent()

    async def create_document(
        self,
        title: str,
        content_request: str,
        sources: Optional[List[Source]] = None
    ) -> Dict:
        """
        Create a Google Doc from natural language request

        Args:
            title: Document title
            content_request: Natural language description of content
            sources: Optional list of sources for citations

        Returns:
            Dictionary with document ID and URL
        """
        try:
            # Generate content using LLM
            prompt = f"""Create a professional document with the following:

Title: {title}

Content Requirements:
{content_request}

Please structure the document with:
1. Introduction
2. Main sections with clear headings
3. Conclusion
4. Citations (if sources provided)

Format in markdown with proper headings (# ## ###)"""

            # Get LLM response
            response = await self.llm.ainvoke(
                prompt,
                callbacks=[self.langfuse_handler]
            )

            markdown_content = response.content

            # Create Google Doc
            doc_id = self.docs_tools.create_document(title)

            # Insert content
            self.docs_tools.markdown_to_docs(
                doc_id,
                markdown_content,
                citations=sources
            )

            # Generate URL
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

            return {
                'document_id': doc_id,
                'document_url': doc_url,
                'title': title,
                'content_preview': markdown_content[:500]
            }

        except Exception as e:
            print(f"Docs creation error: {e}")
            raise
```

### 3. Google Sheets Agent Implementation

**File**: `backend/app/agents/sheets_agent.py`

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from typing import Dict, List, Optional
from app.agents.base import BaseAgent

class SheetsAgent(BaseAgent):
    """Agent for Google Sheets data analysis and visualization"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        credentials: Credentials,
        llm_provider: str = "openai",
        model: str = "gpt-4"
    ):
        super().__init__(user_id, session_id, llm_provider, model)

        # Initialize Google Sheets service
        self.service = build('sheets', 'v4', credentials=credentials)

    async def create_spreadsheet(
        self,
        title: str,
        data: List[List],
        headers: Optional[List[str]] = None
    ) -> Dict:
        """
        Create a Google Sheet with data

        Args:
            title: Spreadsheet title
            data: 2D array of data
            headers: Optional column headers

        Returns:
            Dictionary with spreadsheet ID and URL
        """
        try:
            # Create spreadsheet
            spreadsheet = {
                'properties': {'title': title},
                'sheets': [{
                    'properties': {'title': 'Sheet1'}
                }]
            }

            sheet = self.service.spreadsheets().create(
                body=spreadsheet
            ).execute()

            spreadsheet_id = sheet['spreadsheetId']

            # Prepare data with headers
            values = []
            if headers:
                values.append(headers)
            values.extend(data)

            # Insert data
            body = {'values': values}
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A1',
                valueInputOption='RAW',
                body=body
            ).execute()

            # Generate URL
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

            return {
                'spreadsheet_id': spreadsheet_id,
                'spreadsheet_url': sheet_url,
                'title': title
            }

        except Exception as e:
            print(f"Sheets creation error: {e}")
            raise
```

### 4. Google Slides Agent Implementation

**File**: `backend/app/agents/slides_agent.py`

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from typing import Dict, List
from app.agents.base import BaseAgent

class SlidesAgent(BaseAgent):
    """Agent for Google Slides presentation generation"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        credentials: Credentials,
        llm_provider: str = "openai",
        model: str = "gpt-4"
    ):
        super().__init__(user_id, session_id, llm_provider, model)

        # Initialize Google Slides service
        self.service = build('slides', 'v1', credentials=credentials)

    async def create_presentation(
        self,
        title: str,
        outline: List[Dict[str, str]]
    ) -> Dict:
        """
        Create a Google Slides presentation

        Args:
            title: Presentation title
            outline: List of slide dictionaries with 'title' and 'content'

        Returns:
            Dictionary with presentation ID and URL
        """
        try:
            # Create presentation
            presentation = {
                'title': title
            }

            slides_obj = self.service.presentations().create(
                body=presentation
            ).execute()

            presentation_id = slides_obj['presentationId']

            # Add slides based on outline
            requests = []

            for i, slide_data in enumerate(outline):
                # Create slide
                slide_id = f'slide_{i}'
                requests.append({
                    'createSlide': {
                        'objectId': slide_id,
                        'slideLayoutReference': {
                            'predefinedLayout': 'TITLE_AND_BODY'
                        }
                    }
                })

                # Add title and content (simplified)
                # In production, use proper text insertion APIs

            # Execute requests
            if requests:
                self.service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={'requests': requests}
                ).execute()

            # Generate URL
            slides_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"

            return {
                'presentation_id': presentation_id,
                'presentation_url': slides_url,
                'title': title,
                'slide_count': len(outline)
            }

        except Exception as e:
            print(f"Slides creation error: {e}")
            raise
```

---

## Testing

### Unit Tests

**File**: `backend/tests/agents/test_research_agent.py`

```python
import pytest
from app.agents.research_agent import ResearchAgent

@pytest.mark.asyncio
async def test_research_agent_basic():
    """Test basic research functionality"""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session"
    )

    result = await agent.research("What is LangChain?")

    assert result is not None
    assert 'answer' in result
    assert 'citations' in result
    assert len(result['answer']) > 0

@pytest.mark.asyncio
async def test_research_with_citations():
    """Test research with citation tracking"""
    agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session"
    )

    result = await agent.research_with_citation(
        "Explain quantum computing",
        include_urls=True
    )

    assert '## Sources' in result['answer']
    assert result['bibliography'] is not None
```

### Integration Tests

**File**: `backend/tests/agents/test_integration.py`

```python
import pytest
from app.agents.research_agent import ResearchAgent
from app.agents.docs_agent import DocsAgent

@pytest.mark.asyncio
async def test_research_to_docs_workflow():
    """Test complete workflow: research → docs creation"""

    # Step 1: Research
    research_agent = ResearchAgent(
        user_id="test_user",
        session_id="test_session"
    )

    research_result = await research_agent.research(
        "Benefits of renewable energy"
    )

    # Step 2: Create document from research
    docs_agent = DocsAgent(
        user_id="test_user",
        session_id="test_session",
        credentials=get_test_credentials()
    )

    doc_result = await docs_agent.create_document(
        title="Renewable Energy Report",
        content_request=research_result['answer'],
        sources=research_result['citations']
    )

    assert doc_result['document_id'] is not None
    assert 'document_url' in doc_result
```

### E2E Tests

```bash
# Run all agent tests
pytest backend/tests/agents/ -v

# Run with coverage
pytest backend/tests/agents/ --cov=app/agents --cov-report=html

# Run integration tests only
pytest backend/tests/agents/test_integration.py -v
```

---

## Deployment

### 1. Environment Configuration

```bash
# backend/.env
# Google OAuth
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# LangFuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 2. Database Migration

```bash
cd backend

# Run migrations
alembic upgrade head

# Verify
python -c "from app.db.session import engine; print(engine.table_names())"
```

### 3. Service Deployment

```bash
# Start backend
cd backend
uvicorn app.main:app --reload --port 8000

# Start Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# Start Redis
redis-server
```

### 4. Verification

```bash
# Test agents API
curl http://localhost:8000/api/v1/agents/research \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Test query"}'

# Check LangFuse dashboard
open https://cloud.langfuse.com
```

---

## Success Criteria

### Technical Metrics
- ✅ 4개 Agent 모두 정상 작동
- ✅ Web 검색 정확도 90%+
- ✅ 문서 생성 성공률 100%
- ✅ 평균 응답 시간 < 30초
- ✅ Test Coverage 80%+

### Quality Metrics
- ✅ Citation 정확도 95%+
- ✅ Document Quality Score 90%+
- ✅ LangFuse 모니터링 정상
- ✅ 에러 발생률 < 1%

### Validation Checklist
- [ ] Research Agent: 검색 및 인용 정상
- [ ] Docs Agent: 문서 생성 및 포맷팅 정상
- [ ] Sheets Agent: 데이터 분석 및 차트 생성 정상
- [ ] Slides Agent: 프레젠테이션 생성 정상
- [ ] LangFuse 대시보드: 모든 호출 추적
- [ ] E2E 테스트: 전체 워크플로우 성공

---

## Troubleshooting

### Common Issues

**1. Google API 403 Error**
```bash
# Check OAuth scopes
scopes = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive.file'
]
```

**2. Web Search Timeout**
```python
# Increase timeout in web search
await page.goto(url, timeout=30000)  # 30 seconds
```

**3. LangChain Tool Error**
```python
# Verify tool format
assert tool.name
assert tool.description
assert callable(tool.func)
```

---

## Next Steps

After completing Phase 1:
1. **Monitoring**: 모든 Agent가 LangFuse에서 추적되는지 확인
2. **Optimization**: 느린 Agent 성능 개선
3. **Testing**: 더 많은 Edge Case 테스트 추가
4. **Phase 3**: Mobile Client 구현 시작

---

## References

- [LangChain Documentation](https://python.langchain.com/docs/)
- [Google Workspace APIs](https://developers.google.com/workspace)
- [PHASE_PLAN.md](PHASE_PLAN.md) - 전체 로드맵
- [PHASE_0_IMPLEMENTATION.md](PHASE_0_IMPLEMENTATION.md) - LangChain/LangFuse 통합
- [PHASE_2_IMPLEMENTATION.md](PHASE_2_IMPLEMENTATION.md) - Memory & Citation
