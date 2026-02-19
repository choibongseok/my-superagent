"""Tests for QAResult model and its relationship with Task."""

import pytest
from uuid import uuid4
from datetime import datetime

from app.models import Task, QAResult, User, TaskType, TaskStatus


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing."""
    user = User(
        email="test@example.com",
        full_name="Test User",
        google_id="google_123",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_task(db_session, sample_user):
    """Create a sample task for testing."""
    task = Task(
        user_id=sample_user.id,
        prompt="Test prompt",
        task_type=TaskType.DOCS,
        status=TaskStatus.COMPLETED,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


class TestQAResultModel:
    """Test QAResult model basic functionality."""

    def test_create_qa_result(self, db_session, sample_task):
        """Test creating a QAResult instance."""
        qa_result = QAResult(
            task_id=sample_task.id,
            overall_score=85.5,
            grammar_score=90.0,
            fact_check_score=80.0,
            structure_score=85.0,
            readability_score=88.0,
            completeness_score=82.0,
            confidence_level="high",
            confidence_score=0.92,
            validator_version="1.0.0",
            validation_time_ms=1250,
        )
        db_session.add(qa_result)
        db_session.commit()
        db_session.refresh(qa_result)

        assert qa_result.id is not None
        assert qa_result.task_id == sample_task.id
        assert qa_result.overall_score == 85.5
        assert qa_result.confidence_level == "high"

    def test_qa_result_to_dict(self, db_session, sample_task):
        """Test QAResult.to_dict() method."""
        qa_result = QAResult(
            task_id=sample_task.id,
            overall_score=75.0,
            grammar_score=80.0,
            confidence_level="medium",
            confidence_score=0.75,
            validator_version="1.0.0",
        )
        db_session.add(qa_result)
        db_session.commit()
        db_session.refresh(qa_result)

        result_dict = qa_result.to_dict()
        
        assert result_dict["task_id"] == str(sample_task.id)
        assert result_dict["overall_score"] == 75.0
        assert result_dict["scores"]["grammar"] == 80.0
        assert result_dict["confidence"]["level"] == "medium"

    def test_qa_result_get_grade(self, db_session, sample_task):
        """Test grade calculation."""
        test_cases = [
            (95.0, "A"),
            (85.0, "B"),
            (75.0, "C"),
            (65.0, "D"),
            (50.0, "F"),
        ]

        for score, expected_grade in test_cases:
            qa_result = QAResult(
                task_id=sample_task.id,
                overall_score=score,
                confidence_level="high",
                confidence_score=0.9,
                validator_version="1.0.0",
            )
            assert qa_result.get_grade() == expected_grade

    def test_qa_result_needs_improvement(self, db_session, sample_task):
        """Test needs_improvement() method."""
        qa_good = QAResult(
            task_id=sample_task.id,
            overall_score=85.0,
            confidence_level="high",
            confidence_score=0.9,
            validator_version="1.0.0",
        )
        assert not qa_good.needs_improvement()

        qa_poor = QAResult(
            task_id=sample_task.id,
            overall_score=65.0,
            confidence_level="medium",
            confidence_score=0.7,
            validator_version="1.0.0",
        )
        assert qa_poor.needs_improvement()


class TestTaskQAResultRelationship:
    """Test relationship between Task and QAResult."""

    def test_task_qa_results_relationship(self, db_session, sample_task):
        """Test Task.qa_results relationship."""
        # Create multiple QA results for the same task
        qa1 = QAResult(
            task_id=sample_task.id,
            overall_score=85.0,
            confidence_level="high",
            confidence_score=0.9,
            validator_version="1.0.0",
        )
        qa2 = QAResult(
            task_id=sample_task.id,
            overall_score=90.0,
            confidence_level="high",
            confidence_score=0.95,
            validator_version="1.1.0",
        )
        db_session.add_all([qa1, qa2])
        db_session.commit()
        
        # Refresh task to load relationships
        db_session.refresh(sample_task)
        
        # Check relationship
        assert len(sample_task.qa_results) == 2
        assert qa1 in sample_task.qa_results
        assert qa2 in sample_task.qa_results

    def test_qa_result_task_relationship(self, db_session, sample_task):
        """Test QAResult.task relationship."""
        qa_result = QAResult(
            task_id=sample_task.id,
            overall_score=85.0,
            confidence_level="high",
            confidence_score=0.9,
            validator_version="1.0.0",
        )
        db_session.add(qa_result)
        db_session.commit()
        db_session.refresh(qa_result)
        
        # Check back-reference
        assert qa_result.task.id == sample_task.id
        assert qa_result.task.prompt == sample_task.prompt

    def test_cascade_delete(self, db_session, sample_task):
        """Test that deleting a task cascades to QA results."""
        # Create QA results
        qa1 = QAResult(
            task_id=sample_task.id,
            overall_score=85.0,
            confidence_level="high",
            confidence_score=0.9,
            validator_version="1.0.0",
        )
        qa2 = QAResult(
            task_id=sample_task.id,
            overall_score=90.0,
            confidence_level="high",
            confidence_score=0.95,
            validator_version="1.1.0",
        )
        db_session.add_all([qa1, qa2])
        db_session.commit()
        
        qa1_id = qa1.id
        qa2_id = qa2.id
        
        # Delete the task
        db_session.delete(sample_task)
        db_session.commit()
        
        # Verify QA results are also deleted
        assert db_session.get(QAResult, qa1_id) is None
        assert db_session.get(QAResult, qa2_id) is None
