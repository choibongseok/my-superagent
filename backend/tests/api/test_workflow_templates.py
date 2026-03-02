"""
Tests for Workflow Template API
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid import uuid4

from app.main import app
from app.models.user import User
from app.models.workflow_template import WorkflowTemplate, WorkflowExecution


@pytest.fixture
def test_user(db: Session):
    """Create a test user"""
    user = User(
        id=uuid4(),
        email="test@example.com",
        full_name="Test User",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User):
    """Create authentication headers"""
    # Mock JWT token
    return {"Authorization": f"Bearer mock_token_{test_user.id}"}


@pytest.fixture
def sample_template(db: Session, test_user: User):
    """Create a sample workflow template"""
    template = WorkflowTemplate(
        name="Test Template",
        description="A test workflow template",
        version="v1",
        steps=[
            {
                "id": "step1",
                "agent_type": "research",
                "description": "Research step",
                "inputs": {"query": "{{company_name}}"},
                "depends_on": [],
            },
            {
                "id": "step2",
                "agent_type": "sheets",
                "description": "Sheets step",
                "inputs": {"title": "{{company_name}} Report", "data": "{{step1.data}}"},
                "depends_on": ["step1"],
            },
        ],
        variables=[
            {
                "name": "company_name",
                "type": "string",
                "description": "Company name",
                "required": True,
            }
        ],
        tags=["test", "research"],
        category="testing",
        is_public=True,
        created_by_id=test_user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


class TestWorkflowTemplateAPI:
    """Test workflow template API endpoints"""
    
    def test_create_workflow_template(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Test creating a workflow template"""
        
        payload = {
            "name": "New Template",
            "description": "A new workflow template",
            "version": "v1",
            "steps": [
                {
                    "id": "step1",
                    "agent_type": "research",
                    "description": "Research step",
                    "inputs": {"query": "{{topic}}"},
                    "depends_on": [],
                }
            ],
            "variables": [
                {
                    "name": "topic",
                    "type": "string",
                    "description": "Research topic",
                    "required": True,
                }
            ],
            "tags": ["new", "test"],
            "category": "testing",
            "is_public": True,
        }
        
        response = client.post("/api/v1/workflow-templates", json=payload, headers=auth_headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"
        assert len(data["steps"]) == 1
        assert len(data["variables"]) == 1
    
    def test_list_workflow_templates(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test listing workflow templates"""
        
        response = client.get("/api/v1/workflow-templates", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["templates"]) >= 1
    
    def test_get_workflow_template(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test getting a specific workflow template"""
        
        response = client.get(f"/api/v1/workflow-templates/{sample_template.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_template.id
        assert data["name"] == sample_template.name
    
    def test_update_workflow_template(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test updating a workflow template"""
        
        payload = {
            "name": "Updated Template",
            "description": "Updated description",
        }
        
        response = client.patch(f"/api/v1/workflow-templates/{sample_template.id}", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Template"
        assert data["description"] == "Updated description"
    
    def test_delete_workflow_template(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test deleting a workflow template"""
        
        response = client.delete(f"/api/v1/workflow-templates/{sample_template.id}", headers=auth_headers)
        
        assert response.status_code == 204
        
        # Verify deletion
        deleted_template = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == sample_template.id).first()
        assert deleted_template is None
    
    def test_execute_workflow_template(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test executing a workflow template"""
        
        payload = {
            "input_variables": {
                "company_name": "Acme Corp"
            }
        }
        
        response = client.post(f"/api/v1/workflow-templates/{sample_template.id}/execute", json=payload, headers=auth_headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["workflow_template_id"] == sample_template.id
        assert data["status"] in ["pending", "running", "completed"]
        assert data["input_variables"]["company_name"] == "Acme Corp"
    
    def test_execute_workflow_missing_variables(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test executing a workflow with missing required variables"""
        
        payload = {
            "input_variables": {}
        }
        
        response = client.post(f"/api/v1/workflow-templates/{sample_template.id}/execute", json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        assert "Missing required variables" in response.json()["detail"]
    
    def test_get_workflow_execution(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, test_user: User, auth_headers: dict):
        """Test getting workflow execution status"""
        
        # Create execution
        execution = WorkflowExecution(
            workflow_template_id=sample_template.id,
            user_id=test_user.id,
            status="running",
            current_step=1,
            total_steps=2,
            input_variables={"company_name": "Acme Corp"},
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        response = client.get(f"/api/v1/workflow-executions/{execution.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == execution.id
        assert data["status"] == "running"
    
    def test_list_workflow_executions(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, test_user: User, auth_headers: dict):
        """Test listing workflow executions"""
        
        # Create executions
        for i in range(3):
            execution = WorkflowExecution(
                workflow_template_id=sample_template.id,
                user_id=test_user.id,
                status="completed" if i < 2 else "failed",
                current_step=2,
                total_steps=2,
                input_variables={"company_name": f"Company {i}"},
            )
            db.add(execution)
        db.commit()
        
        response = client.get("/api/v1/workflow-executions", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3
    
    def test_filter_templates_by_category(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test filtering templates by category"""
        
        response = client.get("/api/v1/workflow-templates?category=testing", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for template in data["templates"]:
            assert template["category"] == "testing"
    
    def test_filter_templates_by_tags(self, client: TestClient, db: Session, sample_template: WorkflowTemplate, auth_headers: dict):
        """Test filtering templates by tags"""
        
        response = client.get("/api/v1/workflow-templates?tags=research", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
    
    def test_private_template_access(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Test that private templates are only visible to creator"""
        
        # Create private template
        private_template = WorkflowTemplate(
            name="Private Template",
            description="A private workflow template",
            version="v1",
            steps=[{"id": "step1", "agent_type": "research", "description": "Test", "inputs": {}, "depends_on": []}],
            variables=[],
            is_public=False,
            created_by_id=test_user.id,
        )
        db.add(private_template)
        db.commit()
        
        # Creator should see it
        response = client.get(f"/api/v1/workflow-templates/{private_template.id}", headers=auth_headers)
        assert response.status_code == 200
        
        # Another user should not see it
        other_user_headers = {"Authorization": f"Bearer mock_token_{uuid4()}"}
        response = client.get(f"/api/v1/workflow-templates/{private_template.id}", headers=other_user_headers)
        assert response.status_code == 403


class TestWorkflowExecutor:
    """Test workflow execution logic"""
    
    def test_variable_substitution(self):
        """Test variable substitution in workflow inputs"""
        from app.services.workflow_executor import WorkflowExecutor
        
        executor = WorkflowExecutor(None)
        
        inputs = {
            "query": "{{company_name}} financial report",
            "date": "{{year}}-{{month}}",
        }
        
        variables = {
            "company_name": "Acme Corp",
            "year": "2026",
            "month": "03",
        }
        
        result = executor._substitute_variables(inputs, variables, {})
        
        assert result["query"] == "Acme Corp financial report"
        assert result["date"] == "2026-03"
    
    def test_step_result_reference(self):
        """Test referencing previous step results"""
        from app.services.workflow_executor import WorkflowExecutor
        
        executor = WorkflowExecutor(None)
        
        inputs = {
            "title": "Report for {{company_name}}",
            "data": "{{step1.data}}",
        }
        
        variables = {"company_name": "Acme Corp"}
        results = {
            "step1": {"success": True, "data": "Research findings..."}
        }
        
        result = executor._substitute_variables(inputs, variables, results)
        
        assert result["title"] == "Report for Acme Corp"
        assert result["data"] == "Research findings..."
    
    def test_conditional_evaluation(self):
        """Test conditional expression evaluation"""
        from app.services.workflow_executor import WorkflowExecutor
        
        executor = WorkflowExecutor(None)
        
        # Test simple condition
        results = {"step1": {"success": True}}
        condition = "{{step1.success}} == True"
        
        result = executor._evaluate_condition(condition, {}, results)
        assert result == True


@pytest.mark.integration
class TestPrebuiltTemplates:
    """Test pre-built workflow templates"""
    
    def test_weekly_report_template(self):
        """Test weekly report generator template structure"""
        from app.services.prebuilt_templates import weekly_report_generator
        
        template = weekly_report_generator()
        
        assert template["name"] == "Weekly Report Generator"
        assert len(template["steps"]) == 3
        assert len(template["variables"]) == 3
        
        # Verify step dependencies
        assert template["steps"][0]["depends_on"] == []
        assert template["steps"][1]["depends_on"] == ["step1_research"]
        assert len(template["steps"][2]["depends_on"]) == 2
    
    def test_competitor_analysis_template(self):
        """Test competitor analysis template structure"""
        from app.services.prebuilt_templates import competitor_analysis
        
        template = competitor_analysis()
        
        assert template["name"] == "Competitor Analysis"
        assert len(template["steps"]) == 3
        assert template["category"] == "analysis"
    
    def test_all_prebuilt_templates(self):
        """Test all pre-built templates are valid"""
        from app.services.prebuilt_templates import get_prebuilt_templates
        
        templates = get_prebuilt_templates()
        
        assert len(templates) == 5
        
        for template in templates:
            assert "name" in template
            assert "steps" in template
            assert "variables" in template
            assert len(template["steps"]) > 0
