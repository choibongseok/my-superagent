"""
Unit tests for WorkflowTemplate model
"""
import pytest
from datetime import datetime
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
        email="test@example.com",
        hashed_password="fake_hash"
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestWorkflowTemplate:
    """Test WorkflowTemplate model"""
    
    def test_create_workflow_template(self, db_session, test_user):
        """Test creating a workflow template"""
        template = WorkflowTemplate(
            name="Test Workflow",
            description="A test workflow",
            version="v1",
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
                    "inputs": {"data": "{{step1.data}}"}
                }
            ],
            variables=[
                {"name": "topic", "type": "string", "required": True}
            ],
            tags=["research", "documentation"],
            category="productivity",
            is_public=True,
            created_by_id=test_user.id
        )
        
        db_session.add(template)
        db_session.commit()
        
        assert template.id is not None
        assert template.name == "Test Workflow"
        assert len(template.steps) == 2
        assert len(template.variables) == 1
    
    def test_workflow_template_relationships(self, db_session, test_user):
        """Test workflow template relationships"""
        template = WorkflowTemplate(
            name="Related Workflow",
            steps=[{"id": "step1", "agent_type": "research"}],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        # Test created_by relationship
        assert template.created_by.email == "test@example.com"
        
        # Test executions relationship
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=1,
            input_variables={"test": "value"}
        )
        db_session.add(execution)
        db_session.commit()
        
        db_session.refresh(template)
        assert len(template.executions) == 1
        assert template.executions[0].status == "pending"
    
    def test_workflow_template_indexing(self, db_session, test_user):
        """Test that indexes are created correctly"""
        # Create multiple templates with different visibility and categories
        public_prod = WorkflowTemplate(
            name="Public Productivity",
            steps=[],
            category="productivity",
            is_public=True,
            created_by_id=test_user.id
        )
        private_research = WorkflowTemplate(
            name="Private Research",
            steps=[],
            category="research",
            is_public=False,
            created_by_id=test_user.id
        )
        
        db_session.add_all([public_prod, private_research])
        db_session.commit()
        
        # Query by category and is_public (should use composite index)
        results = db_session.query(WorkflowTemplate).filter(
            WorkflowTemplate.category == "productivity",
            WorkflowTemplate.is_public == True
        ).all()
        
        assert len(results) >= 1
        assert all(t.is_public for t in results)
    
    def test_workflow_template_validation(self, db_session, test_user):
        """Test workflow template validation"""
        # Test with missing required fields
        with pytest.raises(Exception):
            template = WorkflowTemplate(
                name="Invalid Workflow",
                # Missing steps field
                created_by_id=test_user.id
            )
            db_session.add(template)
            db_session.commit()
    
    def test_workflow_template_versioning(self, db_session, test_user):
        """Test workflow template versioning"""
        v1 = WorkflowTemplate(
            name="Versioned Workflow",
            version="v1",
            steps=[{"id": "step1", "agent_type": "research"}],
            created_by_id=test_user.id
        )
        v2 = WorkflowTemplate(
            name="Versioned Workflow",
            version="v2",
            steps=[
                {"id": "step1", "agent_type": "research"},
                {"id": "step2", "agent_type": "docs"}
            ],
            created_by_id=test_user.id
        )
        
        db_session.add_all([v1, v2])
        db_session.commit()
        
        # Query latest version
        latest = db_session.query(WorkflowTemplate).filter(
            WorkflowTemplate.name == "Versioned Workflow"
        ).order_by(WorkflowTemplate.version.desc()).first()
        
        assert latest.version == "v2"
        assert len(latest.steps) == 2


class TestWorkflowExecution:
    """Test WorkflowExecution model"""
    
    def test_create_workflow_execution(self, db_session, test_user):
        """Test creating a workflow execution"""
        template = WorkflowTemplate(
            name="Test Template",
            steps=[{"id": "step1", "agent_type": "research"}],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            status="pending",
            current_step=0,
            total_steps=1,
            input_variables={"topic": "AI"}
        )
        db_session.add(execution)
        db_session.commit()
        
        assert execution.id is not None
        assert execution.status == "pending"
        assert execution.current_step == 0
        assert execution.input_variables["topic"] == "AI"
    
    def test_execution_status_tracking(self, db_session, test_user):
        """Test execution status transitions"""
        template = WorkflowTemplate(
            name="Status Test",
            steps=[{"id": "step1"}],
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
        
        # Test status progression
        assert execution.status == "pending"
        
        execution.status = "running"
        execution.current_step = 1
        db_session.commit()
        
        db_session.refresh(execution)
        assert execution.status == "running"
        assert execution.current_step == 1
        
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.results = {"step1": {"success": True}}
        db_session.commit()
        
        db_session.refresh(execution)
        assert execution.status == "completed"
        assert execution.completed_at is not None
        assert execution.results["step1"]["success"] is True
    
    def test_execution_error_handling(self, db_session, test_user):
        """Test execution error tracking"""
        template = WorkflowTemplate(
            name="Error Test",
            steps=[{"id": "step1"}],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        execution = WorkflowExecution(
            workflow_template_id=template.id,
            user_id=test_user.id,
            total_steps=1,
            status="running"
        )
        db_session.add(execution)
        db_session.commit()
        
        # Simulate error
        execution.status = "failed"
        execution.error_message = "Agent timeout"
        execution.completed_at = datetime.utcnow()
        db_session.commit()
        
        db_session.refresh(execution)
        assert execution.status == "failed"
        assert "timeout" in execution.error_message.lower()
    
    def test_execution_cascade_delete(self, db_session, test_user):
        """Test that executions are deleted when template is deleted"""
        template = WorkflowTemplate(
            name="Cascade Test",
            steps=[{"id": "step1"}],
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
        
        execution_id = execution.id
        
        # Delete template
        db_session.delete(template)
        db_session.commit()
        
        # Verify execution is also deleted
        deleted_execution = db_session.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id
        ).first()
        
        assert deleted_execution is None
    
    def test_execution_query_by_user_and_status(self, db_session, test_user):
        """Test querying executions by user and status (uses composite index)"""
        template = WorkflowTemplate(
            name="Query Test",
            steps=[{"id": "step1"}],
            created_by_id=test_user.id
        )
        db_session.add(template)
        db_session.commit()
        
        # Create executions with different statuses
        for status in ["pending", "running", "completed", "failed"]:
            execution = WorkflowExecution(
                workflow_template_id=template.id,
                user_id=test_user.id,
                total_steps=1,
                status=status
            )
            db_session.add(execution)
        db_session.commit()
        
        # Query running executions for this user
        running = db_session.query(WorkflowExecution).filter(
            WorkflowExecution.user_id == test_user.id,
            WorkflowExecution.status == "running"
        ).all()
        
        assert len(running) == 1
        assert running[0].status == "running"
