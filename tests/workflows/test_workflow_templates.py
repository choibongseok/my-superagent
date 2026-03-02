"""
Integration tests for workflow templates
Tests end-to-end execution of workflow templates
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.workflow_executor import WorkflowExecutor
from app.models.workflow_template import WorkflowTemplate, WorkflowExecution
from app.models.user import User
from tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session():
    """Create a test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        id="550e8400-e29b-41d4-a716-446655440000",
        email="workflow@example.com",
        hashed_password="fake_hash"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def workflow_executor(db_session):
    """Create a workflow executor instance"""
    return WorkflowExecutor(db_session)


class TestVariableSubstitution:
    """Test variable substitution in workflow steps"""
    
    def test_simple_variable_substitution(self, workflow_executor):
        """Test substitution of simple variables"""
        inputs = {
            "query": "Research about {{topic}}",
            "date": "{{target_date}}"
        }
        input_variables = {
            "topic": "AI Ethics",
            "target_date": "2026-03-01"
        }
        results = {}
        
        substituted = workflow_executor._substitute_variables(
            inputs, input_variables, results
        )
        
        assert substituted["query"] == "Research about AI Ethics"
        assert substituted["date"] == "2026-03-01"
    
    def test_step_result_substitution(self, workflow_executor):
        """Test substitution of values from previous step results"""
        inputs = {
            "summary": "Based on {{step1.data}}, create a report"
        }
        input_variables = {}
        results = {
            "step1": {
                "data": "research findings",
                "sources": ["source1.com"]
            }
        }
        
        substituted = workflow_executor._substitute_variables(
            inputs, input_variables, results
        )
        
        assert "research findings" in substituted["summary"]
    
    def test_nested_variable_substitution(self, workflow_executor):
        """Test substitution of nested dictionary values"""
        inputs = {
            "title": "{{step1.metadata.title}}",
            "count": "{{step1.stats.count}}"
        }
        input_variables = {}
        results = {
            "step1": {
                "metadata": {"title": "Annual Report"},
                "stats": {"count": 42}
            }
        }
        
        substituted = workflow_executor._substitute_variables(
            inputs, input_variables, results
        )
        
        assert substituted["title"] == "Annual Report"
        assert substituted["count"] == "42"
    
    def test_dict_and_list_substitution(self, workflow_executor):
        """Test substitution in nested dicts and lists"""
        inputs = {
            "config": {
                "name": "{{project_name}}",
                "items": ["{{item1}}", "{{item2}}"]
            }
        }
        input_variables = {
            "project_name": "SuperAgent",
            "item1": "feature-a",
            "item2": "feature-b"
        }
        results = {}
        
        substituted = workflow_executor._substitute_variables(
            inputs, input_variables, results
        )
        
        assert substituted["config"]["name"] == "SuperAgent"
        assert substituted["config"]["items"] == ["feature-a", "feature-b"]


class TestConditionalLogic:
    """Test conditional execution in workflows"""
    
    def test_simple_condition_true(self, workflow_executor):
        """Test condition that evaluates to True"""
        condition = "'{{step1.success}}' == 'True'"
        input_variables = {}
        results = {"step1": {"success": True}}
        
        result = workflow_executor._evaluate_condition(
            condition, input_variables, results
        )
        
        assert result is True
    
    def test_simple_condition_false(self, workflow_executor):
        """Test condition that evaluates to False"""
        condition = "'{{step1.success}}' == 'True'"
        input_variables = {}
        results = {"step1": {"success": False}}
        
        result = workflow_executor._evaluate_condition(
            condition, input_variables, results
        )
        
        assert result is False
    
    def test_numeric_comparison(self, workflow_executor):
        """Test numeric comparison in conditions"""
        condition = "int('{{step1.count}}') > 10"
        input_variables = {}
        results = {"step1": {"count": 25}}
        
        result = workflow_executor._evaluate_condition(
            condition, input_variables, results
        )
        
        assert result is True
    
    def test_invalid_condition_returns_false(self, workflow_executor):
        """Test that invalid conditions return False safely"""
        condition = "{{invalid.syntax"
        input_variables = {}
        results = {}
        
        result = workflow_executor._evaluate_condition(
            condition, input_variables, results
        )
        
        assert result is False


class TestWorkflowExecution:
    """Test end-to-end workflow execution"""
    
    @pytest.mark.asyncio
    async def test_simple_workflow_execution(self, db_session, test_user, workflow_executor):
        """Test execution of a simple 2-step workflow"""
        # Create template
        template = WorkflowTemplate(
            name="Simple Research Workflow",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "research",
                    "inputs": {"query": "{{topic}}"}
                },
                {
                    "id": "step2",
                    "agent_type": "docs",
                    "depends_on": ["step1"],
                    "inputs": {"content": "{{step1.data}}"}
                }
            ],
            variables=[
                {"name": "topic", "type": "string", "required": True}
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        # Create execution
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=2,
            input_variables={"topic": "Machine Learning"}
        )
        db_session.add(execution)
        db_session.commit()
        
        # Execute workflow
        results = await workflow_executor.execute_workflow(
            execution.id,
            template,
            {"topic": "Machine Learning"}
        )
        
        # Verify results
        assert "step1" in results
        assert "step2" in results
        assert results["step1"]["success"] is True
        assert results["step2"]["success"] is True
        
        # Verify execution status
        db_session.refresh(execution)
        assert execution.status == "completed"
        assert execution.current_step == 2
        assert execution.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_workflow_with_conditional_step(self, db_session, test_user, workflow_executor):
        """Test workflow with conditional step execution"""
        template = WorkflowTemplate(
            name="Conditional Workflow",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "research",
                    "inputs": {"query": "{{topic}}"}
                },
                {
                    "id": "step2",
                    "agent_type": "sheets",
                    "condition": "'{{step1.success}}' == 'True'",
                    "inputs": {"data": "{{step1.data}}"}
                },
                {
                    "id": "step3",
                    "agent_type": "docs",
                    "condition": "'{{step1.success}}' == 'False'",
                    "inputs": {"error": "Research failed"}
                }
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=3,
            input_variables={"topic": "Test"}
        )
        db_session.add(execution)
        db_session.commit()
        
        results = await workflow_executor.execute_workflow(
            execution.id, template, {"topic": "Test"}
        )
        
        # step1 should run, step2 should run (condition true), step3 should be skipped
        assert results["step1"]["success"] is True
        assert results["step2"]["success"] is True
        assert results["step3"]["skipped"] is True
    
    @pytest.mark.asyncio
    async def test_workflow_with_missing_dependency(self, db_session, test_user, workflow_executor):
        """Test that workflow fails when dependency is missing"""
        template = WorkflowTemplate(
            name="Invalid Dependency",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "research",
                    "inputs": {}
                },
                {
                    "id": "step2",
                    "agent_type": "docs",
                    "depends_on": ["step_nonexistent"],  # Invalid dependency
                    "inputs": {}
                }
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=2
        )
        db_session.add(execution)
        db_session.commit()
        
        with pytest.raises(Exception) as exc_info:
            await workflow_executor.execute_workflow(
                execution.id, template, {}
            )
        
        assert "depends on" in str(exc_info.value)
        
        # Verify execution is marked as failed
        db_session.refresh(execution)
        assert execution.status == "failed"
    
    @pytest.mark.asyncio
    async def test_workflow_error_handling(self, db_session, test_user, workflow_executor):
        """Test error handling in workflow execution"""
        template = WorkflowTemplate(
            name="Error Test Workflow",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "unknown_agent",  # Invalid agent type
                    "inputs": {}
                }
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=1
        )
        db_session.add(execution)
        db_session.commit()
        
        with pytest.raises(Exception):
            await workflow_executor.execute_workflow(
                execution.id, template, {}
            )
        
        # Verify execution status
        db_session.refresh(execution)
        assert execution.status == "failed"
        assert execution.error_message is not None


class TestPreBuiltTemplates:
    """Test pre-built workflow templates"""
    
    @pytest.mark.asyncio
    async def test_weekly_report_template(self, db_session, test_user, workflow_executor):
        """Test 'Weekly Report Generator' template"""
        template = WorkflowTemplate(
            name="Weekly Report Generator",
            description="Research → Sheets → Docs",
            steps=[
                {
                    "id": "research",
                    "agent_type": "research",
                    "inputs": {
                        "query": "{{company_name}} weekly updates {{date_range}}"
                    }
                },
                {
                    "id": "create_sheet",
                    "agent_type": "sheets",
                    "depends_on": ["research"],
                    "inputs": {
                        "title": "Weekly Report - {{company_name}}",
                        "data": "{{research.data}}"
                    }
                },
                {
                    "id": "create_doc",
                    "agent_type": "docs",
                    "depends_on": ["research", "create_sheet"],
                    "inputs": {
                        "title": "Weekly Report - {{company_name}}",
                        "content": "{{research.data}}",
                        "spreadsheet_url": "{{create_sheet.url}}"
                    }
                }
            ],
            variables=[
                {"name": "company_name", "type": "string", "required": True},
                {"name": "date_range", "type": "string", "required": True}
            ],
            tags=["reporting", "weekly", "research"],
            category="reporting",
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=3,
            input_variables={
                "company_name": "Acme Corp",
                "date_range": "March 1-7, 2026"
            }
        )
        db_session.add(execution)
        db_session.commit()
        
        results = await workflow_executor.execute_workflow(
            execution.id, template,
            {"company_name": "Acme Corp", "date_range": "March 1-7, 2026"}
        )
        
        assert results["research"]["success"] is True
        assert results["create_sheet"]["success"] is True
        assert results["create_doc"]["success"] is True
        assert "spreadsheet_123" in results["create_sheet"]["spreadsheet_id"]
    
    @pytest.mark.asyncio
    async def test_competitor_analysis_template(self, db_session, test_user, workflow_executor):
        """Test 'Competitor Analysis' template"""
        template = WorkflowTemplate(
            name="Competitor Analysis",
            description="Research → Sheets with charts",
            steps=[
                {
                    "id": "research_competitors",
                    "agent_type": "research",
                    "inputs": {
                        "query": "{{company_name}} competitors analysis"
                    }
                },
                {
                    "id": "create_analysis_sheet",
                    "agent_type": "sheets",
                    "depends_on": ["research_competitors"],
                    "inputs": {
                        "title": "Competitor Analysis - {{company_name}}",
                        "data": "{{research_competitors.data}}",
                        "create_charts": True
                    }
                }
            ],
            variables=[
                {"name": "company_name", "type": "string", "required": True}
            ],
            tags=["analysis", "competitors", "research"],
            category="analysis",
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=2,
            input_variables={"company_name": "Tech Startup"}
        )
        db_session.add(execution)
        db_session.commit()
        
        results = await workflow_executor.execute_workflow(
            execution.id, template, {"company_name": "Tech Startup"}
        )
        
        assert results["research_competitors"]["success"] is True
        assert results["create_analysis_sheet"]["success"] is True
    
    @pytest.mark.asyncio
    async def test_meeting_prep_template(self, db_session, test_user, workflow_executor):
        """Test 'Meeting Prep' template"""
        template = WorkflowTemplate(
            name="Meeting Prep",
            description="Calendar → Research → Slides",
            steps=[
                {
                    "id": "research_topic",
                    "agent_type": "research",
                    "inputs": {
                        "query": "{{topic}} latest developments"
                    }
                },
                {
                    "id": "create_slides",
                    "agent_type": "slides",
                    "depends_on": ["research_topic"],
                    "inputs": {
                        "title": "Meeting: {{topic}}",
                        "content": "{{research_topic.data}}",
                        "template": "professional"
                    }
                }
            ],
            variables=[
                {"name": "topic", "type": "string", "required": True}
            ],
            tags=["meeting", "presentation"],
            category="productivity",
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=2,
            input_variables={"topic": "AI Ethics"}
        )
        db_session.add(execution)
        db_session.commit()
        
        results = await workflow_executor.execute_workflow(
            execution.id, template, {"topic": "AI Ethics"}
        )
        
        assert results["research_topic"]["success"] is True
        assert results["create_slides"]["success"] is True
        assert "presentation" in results["create_slides"]["presentation_id"]


class TestTemplateVersioning:
    """Test template versioning features"""
    
    def test_multiple_template_versions(self, db_session, test_user):
        """Test creating and querying multiple versions of same template"""
        v1 = WorkflowTemplate(
            name="Evolving Workflow",
            version="v1",
            description="Version 1",
            steps=[{"id": "step1", "agent_type": "research"}],
            created_by_id=test_user.id
        )
        v2 = WorkflowTemplate(
            name="Evolving Workflow",
            version="v2",
            description="Version 2 with improvements",
            steps=[
                {"id": "step1", "agent_type": "research"},
                {"id": "step2", "agent_type": "docs"}
            ],
            created_by_id=test_user.id
        )
        
        db_session.add_all([v1, v2])
        db_session.commit()
        
        # Query all versions
        versions = db_session.query(WorkflowTemplate).filter(
            WorkflowTemplate.name == "Evolving Workflow"
        ).order_by(WorkflowTemplate.version).all()
        
        assert len(versions) == 2
        assert versions[0].version == "v1"
        assert versions[1].version == "v2"
        assert len(versions[1].steps) > len(versions[0].steps)
    
    def test_latest_version_query(self, db_session, test_user):
        """Test querying the latest version of a template"""
        for version in ["v1", "v2", "v3"]:
            template = WorkflowTemplate(
                name="Multi Version",
                version=version,
                steps=[{"id": f"step_{version}"}],
                created_by_id=test_user.id
            )
            db_session.add(template)
        db_session.commit()
        
        latest = db_session.query(WorkflowTemplate).filter(
            WorkflowTemplate.name == "Multi Version"
        ).order_by(WorkflowTemplate.version.desc()).first()
        
        assert latest.version == "v3"


class TestErrorScenarios:
    """Test various error scenarios"""
    
    @pytest.mark.asyncio
    async def test_missing_required_variable(self, db_session, test_user, workflow_executor):
        """Test execution fails gracefully when required variable is missing"""
        template = WorkflowTemplate(
            name="Required Var Test",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "research",
                    "inputs": {"query": "{{required_topic}}"}
                }
            ],
            variables=[
                {"name": "required_topic", "type": "string", "required": True}
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=1,
            input_variables={}  # Missing required_topic
        )
        db_session.add(execution)
        db_session.commit()
        
        results = await workflow_executor.execute_workflow(
            execution.id, template, {}
        )
        
        # Variable substitution should leave placeholder intact
        # Agent should receive "{{required_topic}}" literally
        assert results["step1"] is not None
    
    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self, db_session, test_user, workflow_executor):
        """Test detection of circular dependencies"""
        # Note: Current implementation doesn't explicitly detect circular deps
        # This test documents expected behavior when they occur
        template = WorkflowTemplate(
            name="Circular Dependency",
            steps=[
                {
                    "id": "step1",
                    "agent_type": "research",
                    "depends_on": ["step2"],
                    "inputs": {}
                },
                {
                    "id": "step2",
                    "agent_type": "docs",
                    "depends_on": ["step1"],
                    "inputs": {}
                }
            ],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=2
        )
        db_session.add(execution)
        db_session.commit()
        
        # This should fail because step1 depends on step2 which hasn't run
        with pytest.raises(Exception) as exc_info:
            await workflow_executor.execute_workflow(
                execution.id, template, {}
            )
        
        assert "depends on" in str(exc_info.value)
