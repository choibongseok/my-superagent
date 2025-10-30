"""Agent implementations for AgentHQ.

This module provides agent classes for different task types:
- BaseAgent: Foundation for all agents with LangChain and LangFuse
- ResearchAgent: Web research and analysis with citation tracking
- DocsAgent: Google Docs generation with integrated research
- SheetsAgent: Google Sheets generation (stub)
- SlidesAgent: Google Slides generation (stub)
- MultiAgentOrchestrator: Multi-agent collaboration system (Phase 7)
- TaskPlanner: Autonomous task planning with resource estimation (Phase 7)
"""

from app.agents.base import BaseAgent
from app.agents.research_agent import ResearchAgent
from app.agents.docs_agent import DocsAgent
from app.agents.orchestrator import MultiAgentOrchestrator, AgentTask
from app.agents.task_planner import TaskPlanner, ExecutionPlan, PlanStep
from app.agents.celery_app import celery_app

__all__ = [
    "BaseAgent",
    "ResearchAgent",
    "DocsAgent",
    "MultiAgentOrchestrator",
    "AgentTask",
    "TaskPlanner",
    "ExecutionPlan",
    "PlanStep",
    "celery_app",
]
