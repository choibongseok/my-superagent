"""
Multi-agent workflows for common automation tasks.

This module provides pre-defined workflows that chain multiple agents together.
"""

from app.agents.protocols import (
    AgentRole,
    WorkflowDefinition,
    WorkflowStep,
)


def create_research_to_sheets_workflow() -> WorkflowDefinition:
    """
    Workflow: Research a topic → Extract structured data → Create spreadsheet.
    
    Example:
        Research "AI companies 2026" → Extract company names/funding/stage →
        Create formatted spreadsheet with charts.
    """
    step1 = WorkflowStep(
        agent=AgentRole.RESEARCH,
        task_description="Research the given topic and extract structured data",
        dependencies=[],
        input_mapping={},
    )
    
    step2 = WorkflowStep(
        agent=AgentRole.SHEETS,
        task_description="Create a spreadsheet from the research data with formatting and charts",
        dependencies=[step1.step_id],
        input_mapping={
            "data": "results",  # Map research results to sheets data
        },
        error_handling="stop",
    )
    
    workflow = WorkflowDefinition(
        name="Research to Spreadsheet",
        description="Research a topic and automatically create a formatted Google Sheet",
        steps=[step1, step2],
        initial_inputs={
            "query": "",  # User provides this
        },
        metadata={
            "category": "research",
            "estimated_duration_seconds": 60,
            "requires_google_auth": True,
        },
    )
    
    return workflow


def create_research_to_docs_workflow() -> WorkflowDefinition:
    """
    Workflow: Research a topic → Generate report with citations → Create Google Doc.
    
    Example:
        Research "Quantum computing trends" → Generate 2-page report →
        Create formatted Google Doc with table of contents.
    """
    step1 = WorkflowStep(
        agent=AgentRole.RESEARCH,
        task_description="Research the given topic comprehensively with multiple sources",
        dependencies=[],
        input_mapping={},
    )
    
    step2 = WorkflowStep(
        agent=AgentRole.DOCS,
        task_description="Create a professional research report in Google Docs with citations and formatting",
        dependencies=[step1.step_id],
        input_mapping={
            "research_data": "results",
            "citations": "sources",
        },
        error_handling="stop",
    )
    
    workflow = WorkflowDefinition(
        name="Research to Document",
        description="Research a topic and generate a professional report in Google Docs",
        steps=[step1, step2],
        initial_inputs={
            "query": "",  # User provides this
            "report_style": "academic",  # or "business", "technical"
        },
        metadata={
            "category": "research",
            "estimated_duration_seconds": 90,
            "requires_google_auth": True,
        },
    )
    
    return workflow


def create_full_pipeline_workflow() -> WorkflowDefinition:
    """
    Workflow: Research → Spreadsheet → Presentation.
    
    Full pipeline for creating a complete research deliverable.
    
    Example:
        Research "Electric vehicle market 2026" →
        Create data spreadsheet with charts →
        Generate presentation slides with key findings.
    """
    step1 = WorkflowStep(
        agent=AgentRole.RESEARCH,
        task_description="Comprehensive research on the given topic with data extraction",
        dependencies=[],
    )
    
    step2 = WorkflowStep(
        agent=AgentRole.SHEETS,
        task_description="Create spreadsheet with data tables and visualization charts",
        dependencies=[step1.step_id],
        input_mapping={
            "data": "results",
        },
    )
    
    step3 = WorkflowStep(
        agent=AgentRole.SLIDES,
        task_description="Create presentation slides highlighting key findings and charts from spreadsheet",
        dependencies=[step1.step_id, step2.step_id],
        input_mapping={
            "findings": "summary",  # From research
            "charts": "chart_ids",  # From sheets
        },
        error_handling="skip",  # Continue even if slides fail
    )
    
    workflow = WorkflowDefinition(
        name="Full Research Pipeline",
        description="Complete research workflow: Research → Spreadsheet → Presentation",
        steps=[step1, step2, step3],
        initial_inputs={
            "query": "",  # User provides this
            "include_charts": True,
            "presentation_theme": "modern",
        },
        metadata={
            "category": "research",
            "estimated_duration_seconds": 180,
            "requires_google_auth": True,
            "complexity": "high",
        },
    )
    
    return workflow


# Registry of available workflows
WORKFLOW_REGISTRY = {
    "research_to_sheets": create_research_to_sheets_workflow,
    "research_to_docs": create_research_to_docs_workflow,
    "full_pipeline": create_full_pipeline_workflow,
}


def get_workflow(workflow_id: str) -> WorkflowDefinition:
    """
    Get a workflow by ID.
    
    Args:
        workflow_id: ID of the workflow (e.g., "research_to_sheets")
        
    Returns:
        WorkflowDefinition instance
        
    Raises:
        KeyError: If workflow not found
    """
    factory = WORKFLOW_REGISTRY.get(workflow_id)
    if not factory:
        raise KeyError(f"Workflow not found: {workflow_id}")
    return factory()


def list_workflows() -> list[dict]:
    """
    List all available workflows.
    
    Returns:
        List of workflow metadata dicts
    """
    workflows = []
    for workflow_id, factory in WORKFLOW_REGISTRY.items():
        workflow = factory()
        workflows.append({
            "id": workflow_id,
            "name": workflow.name,
            "description": workflow.description,
            "steps": len(workflow.steps),
            "metadata": workflow.metadata,
        })
    return workflows
