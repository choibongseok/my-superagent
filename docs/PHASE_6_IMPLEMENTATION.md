# Phase 6 Implementation Guide: Advanced Features

> **목표**: 차별화 기능 및 플랫폼 확장성 강화
> **기간**: 3주
> **우선순위**: P2 (Nice to Have)

---

## Overview

Phase 6는 AgentHQ의 고급 기능 및 생태계 확장을 구현합니다.

### Key Features
- ✅ **Template Marketplace**: 사용자 템플릿 공유
- ✅ **Multi-Agent Collaboration**: 여러 Agent 협업
- ✅ **Autonomous Task Planning**: AI 기반 작업 계획
- ✅ **Plugin System**: 확장 가능한 플러그인 아키텍처
- ✅ **Custom Tools**: 사용자 정의 도구
- ✅ **Quality Assurance Agent**: 자동 품질 검증

---

## Implementation

### 1. Template Marketplace

#### Template Model

**File**: `backend/app/models/template.py`

```python
from sqlalchemy import Column, String, Text, JSON, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseModel

class Template(BaseModel):
    """Template model"""
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100))  # docs, sheets, slides, research
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Template content
    prompt_template = Column(Text, nullable=False)
    parameters = Column(JSON)  # Input parameters schema
    example_inputs = Column(JSON)  # Example inputs
    example_outputs = Column(JSON)  # Example outputs

    # Metadata
    is_public = Column(Boolean, default=False)
    is_official = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    rating = Column(Float, default=0.0)
    tags = Column(JSON)  # Array of tags

    # Versioning
    version = Column(String(20), default="1.0.0")
    changelog = Column(Text)
```

#### Template Service

**File**: `backend/app/services/template_service.py`

```python
from typing import List, Optional
from uuid import UUID
from app.models.template import Template

class TemplateService:
    """Service for template management"""

    async def create_template(
        self,
        name: str,
        description: str,
        category: str,
        author_id: UUID,
        prompt_template: str,
        parameters: dict,
        is_public: bool = False
    ) -> Template:
        """Create a new template"""
        template = Template(
            name=name,
            description=description,
            category=category,
            author_id=author_id,
            prompt_template=prompt_template,
            parameters=parameters,
            is_public=is_public
        )
        self.db.add(template)
        await self.db.commit()
        return template

    async def get_public_templates(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Template]:
        """Get public templates"""
        query = select(Template).where(Template.is_public == True)

        if category:
            query = query.where(Template.category == category)

        if tags:
            # Filter by tags (JSON array contains)
            for tag in tags:
                query = query.where(Template.tags.contains([tag]))

        query = query.order_by(Template.usage_count.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def use_template(
        self,
        template_id: UUID,
        inputs: dict,
        user_id: UUID
    ) -> dict:
        """Use a template with inputs"""
        template = await self.get_template(template_id)

        # Increment usage count
        template.usage_count += 1
        await self.db.commit()

        # Replace variables in prompt template
        prompt = template.prompt_template
        for key, value in inputs.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        # Create task using the prompt
        task = await create_task(
            user_id=user_id,
            prompt=prompt,
            output_type=template.category
        )

        return {
            'template_id': template_id,
            'task_id': task.id,
            'prompt': prompt
        }
```

### 2. Multi-Agent Collaboration

**File**: `backend/app/agents/multi_agent_system.py`

```python
from langchain.agents import AgentExecutor
from typing import List, Dict
from app.agents.research_agent import ResearchAgent
from app.agents.docs_agent import DocsAgent

class MultiAgentOrchestrator:
    """Orchestrate multiple agents for complex tasks"""

    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id

        # Initialize agents
        self.research_agent = ResearchAgent(user_id, session_id)
        self.docs_agent = DocsAgent(user_id, session_id, credentials=None)

    async def execute_complex_task(
        self,
        task_description: str
    ) -> Dict:
        """Execute a complex task requiring multiple agents"""

        # Step 1: Plan the task
        plan = await self._plan_task(task_description)

        # Step 2: Execute each step with appropriate agent
        results = []
        for step in plan['steps']:
            agent_type = step['agent']
            task = step['task']

            if agent_type == "research":
                result = await self.research_agent.research(task)
            elif agent_type == "docs":
                result = await self.docs_agent.create_document(
                    title=step.get('title', 'Document'),
                    content_request=task
                )
            # Add more agents...

            results.append({
                'step': step,
                'result': result
            })

        # Step 3: Synthesize final output
        final_output = await self._synthesize_results(results)

        return {
            'plan': plan,
            'results': results,
            'final_output': final_output
        }

    async def _plan_task(self, task_description: str) -> Dict:
        """Plan task execution using LLM"""
        planning_prompt = f"""Break down this task into steps:

Task: {task_description}

For each step, identify:
1. The required agent (research, docs, sheets, slides)
2. The specific task for that agent
3. Dependencies on previous steps

Output as JSON with structure:
{{
  "steps": [
    {{
      "agent": "research",
      "task": "Research X",
      "dependencies": []
    }},
    ...
  ]
}}"""

        response = await self.research_agent.llm.ainvoke(planning_prompt)
        plan = json.loads(response.content)
        return plan

    async def _synthesize_results(self, results: List[Dict]) -> str:
        """Synthesize results from multiple agents"""
        synthesis_prompt = f"""Synthesize these results into a coherent summary:

Results:
{json.dumps(results, indent=2)}

Provide a comprehensive summary of what was accomplished."""

        response = await self.research_agent.llm.ainvoke(synthesis_prompt)
        return response.content
```

### 3. Autonomous Task Planning

**File**: `backend/app/agents/task_planner.py`

```python
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from typing import List, Dict

class TaskPlanner:
    """Plan tasks autonomously"""

    def __init__(self, llm):
        self.llm = llm

        # Planning prompt
        self.planning_prompt = PromptTemplate(
            input_variables=["goal", "context"],
            template="""You are an intelligent task planner. Given a goal, create a detailed execution plan.

Goal: {goal}

Context: {context}

Create a step-by-step plan with:
1. Task breakdown
2. Estimated time per task
3. Required resources
4. Success criteria
5. Potential risks

Output as JSON:
{{
  "steps": [
    {{
      "id": 1,
      "task": "Task description",
      "estimated_time": "30 minutes",
      "resources": ["Agent", "API"],
      "success_criteria": "Specific outcome",
      "risks": ["Potential issue"]
    }}
  ]
}}"""
        )

        self.chain = LLMChain(llm=self.llm, prompt=self.planning_prompt)

    async def plan(self, goal: str, context: dict = None) -> Dict:
        """Create execution plan"""
        result = await self.chain.ainvoke({
            "goal": goal,
            "context": json.dumps(context or {})
        })

        plan = json.loads(result['text'])
        return plan

    async def execute_plan(
        self,
        plan: Dict,
        agents: dict
    ) -> List[Dict]:
        """Execute a plan using available agents"""
        results = []

        for step in plan['steps']:
            # Select appropriate agent
            agent = self._select_agent(step, agents)

            # Execute step
            result = await agent.execute(step['task'])

            # Check success criteria
            success = self._validate_success(result, step['success_criteria'])

            results.append({
                'step': step,
                'result': result,
                'success': success
            })

            # Stop if step fails
            if not success:
                break

        return results
```

### 4. Plugin System

#### Plugin Interface

**File**: `backend/app/plugins/base.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class BasePlugin(ABC):
    """Base class for plugins"""

    def __init__(self, config: dict):
        self.config = config
        self.name = self.__class__.__name__
        self.version = "1.0.0"

    @abstractmethod
    async def initialize(self):
        """Initialize plugin"""
        pass

    @abstractmethod
    async def execute(self, inputs: dict) -> dict:
        """Execute plugin"""
        pass

    @abstractmethod
    def get_manifest(self) -> dict:
        """Get plugin manifest"""
        return {
            'name': self.name,
            'version': self.version,
            'description': '',
            'author': '',
            'permissions': [],
            'inputs': {},
            'outputs': {}
        }

    async def cleanup(self):
        """Cleanup resources"""
        pass
```

#### Plugin Manager

**File**: `backend/app/plugins/manager.py`

```python
from typing import Dict, List
import importlib
import os

class PluginManager:
    """Manage plugins"""

    def __init__(self):
        self.plugins: Dict[str, BasePlugin] = {}

    async def load_plugin(self, plugin_path: str, config: dict = None):
        """Load a plugin"""
        try:
            # Import plugin module
            module = importlib.import_module(plugin_path)

            # Get plugin class
            plugin_class = getattr(module, 'Plugin')

            # Initialize plugin
            plugin = plugin_class(config or {})
            await plugin.initialize()

            # Register plugin
            self.plugins[plugin.name] = plugin

            return plugin

        except Exception as e:
            print(f"Error loading plugin {plugin_path}: {e}")
            raise

    async def execute_plugin(
        self,
        plugin_name: str,
        inputs: dict
    ) -> dict:
        """Execute a plugin"""
        if plugin_name not in self.plugins:
            raise ValueError(f"Plugin {plugin_name} not found")

        plugin = self.plugins[plugin_name]
        return await plugin.execute(inputs)

    def list_plugins(self) -> List[dict]:
        """List all loaded plugins"""
        return [
            plugin.get_manifest()
            for plugin in self.plugins.values()
        ]

    async def unload_plugin(self, plugin_name: str):
        """Unload a plugin"""
        if plugin_name in self.plugins:
            await self.plugins[plugin_name].cleanup()
            del self.plugins[plugin_name]
```

#### Example Plugin

**File**: `plugins/slack_notifier.py`

```python
from app.plugins.base import BasePlugin
from slack_sdk.web.async_client import AsyncWebClient

class Plugin(BasePlugin):
    """Slack notification plugin"""

    async def initialize(self):
        """Initialize Slack client"""
        self.client = AsyncWebClient(
            token=self.config.get('slack_token')
        )

    async def execute(self, inputs: dict) -> dict:
        """Send Slack notification"""
        channel = inputs.get('channel')
        message = inputs.get('message')

        response = await self.client.chat_postMessage(
            channel=channel,
            text=message
        )

        return {
            'success': response['ok'],
            'ts': response['ts']
        }

    def get_manifest(self) -> dict:
        return {
            'name': 'SlackNotifier',
            'version': '1.0.0',
            'description': 'Send notifications to Slack',
            'author': 'AgentHQ',
            'permissions': ['network.http'],
            'inputs': {
                'channel': 'string',
                'message': 'string'
            },
            'outputs': {
                'success': 'boolean',
                'ts': 'string'
            }
        }
```

### 5. Quality Assurance Agent

**File**: `backend/app/agents/qa_agent.py`

```python
from app.agents.base import BaseAgent

class QAAgent(BaseAgent):
    """Quality assurance agent"""

    def __init__(self, user_id: str, session_id: str):
        super().__init__(user_id, session_id)

    async def validate_output(
        self,
        output: str,
        criteria: dict
    ) -> dict:
        """Validate output against criteria"""

        validation_prompt = f"""Validate this output against the following criteria:

Output:
{output}

Criteria:
{json.dumps(criteria, indent=2)}

For each criterion, check if it's met and provide feedback.

Output as JSON:
{{
  "overall_pass": true/false,
  "checks": [
    {{
      "criterion": "Criterion name",
      "passed": true/false,
      "feedback": "Detailed feedback"
    }}
  ],
  "score": 0-100,
  "recommendations": ["Improvement 1", "Improvement 2"]
}}"""

        response = await self.llm.ainvoke(validation_prompt)
        validation = json.loads(response.content)

        return validation

    async def suggest_improvements(
        self,
        content: str,
        content_type: str
    ) -> List[str]:
        """Suggest improvements"""

        prompt = f"""Analyze this {content_type} and suggest improvements:

Content:
{content}

Provide specific, actionable suggestions to improve:
1. Clarity
2. Completeness
3. Accuracy
4. Formatting
5. Style

Output as JSON array of suggestions."""

        response = await self.llm.ainvoke(prompt)
        suggestions = json.loads(response.content)

        return suggestions
```

---

## Testing

### Plugin Tests

```python
@pytest.mark.asyncio
async def test_load_plugin():
    manager = PluginManager()

    await manager.load_plugin(
        'plugins.slack_notifier',
        config={'slack_token': 'test-token'}
    )

    plugins = manager.list_plugins()
    assert len(plugins) == 1
    assert plugins[0]['name'] == 'SlackNotifier'
```

### Multi-Agent Tests

```python
@pytest.mark.asyncio
async def test_multi_agent_collaboration():
    orchestrator = MultiAgentOrchestrator(
        user_id="test",
        session_id="test"
    )

    result = await orchestrator.execute_complex_task(
        "Research renewable energy and create a comprehensive report"
    )

    assert 'plan' in result
    assert 'results' in result
    assert 'final_output' in result
```

---

## Success Criteria

### Features
- ✅ Template marketplace with 50+ templates
- ✅ Multi-agent collaboration working
- ✅ Plugin system supporting 10+ plugins
- ✅ QA agent validation accuracy 90%+

### User Adoption
- ✅ 100+ user-created templates
- ✅ 1000+ template uses per month
- ✅ 20+ community plugins

---

## Next Steps

- **Ecosystem Growth**: Community engagement
- **Enterprise Features**: Advanced security, compliance
- **AI Improvements**: Better planning, self-correction

---

## References

- [LangChain Agents](https://python.langchain.com/docs/modules/agents/)
- [Plugin Architecture](https://realpython.com/python-application-layouts/)
- [PHASE_PLAN.md](PHASE_PLAN.md)
