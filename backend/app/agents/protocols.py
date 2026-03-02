"""
Agent communication protocols for multi-agent collaboration.

This module defines the message passing protocol used by the AgentCoordinator
to enable agents to communicate and delegate tasks to each other.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class AgentRole(str, Enum):
    """Available agent roles in the system."""
    
    RESEARCH = "research"
    DOCS = "docs"
    SHEETS = "sheets"
    SLIDES = "slides"
    FACT_CHECKER = "fact_checker"
    COORDINATOR = "coordinator"


class MessageStatus(str, Enum):
    """Status of agent message/response."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELEGATED = "delegated"


@dataclass
class AgentMessage:
    """
    Message sent from one agent to another.
    
    Example:
        >>> msg = AgentMessage(
        ...     sender=AgentRole.RESEARCH,
        ...     receiver=AgentRole.SHEETS,
        ...     payload={"data": [{"name": "Alice", "score": 95}]},
        ...     task_description="Create spreadsheet from research data"
        ... )
    """
    
    sender: AgentRole
    receiver: AgentRole
    payload: Dict[str, Any]
    task_description: str
    message_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_message_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for serialization."""
        return {
            "message_id": self.message_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "payload": self.payload,
            "task_description": self.task_description,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "parent_message_id": self.parent_message_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Create message from dictionary."""
        return cls(
            message_id=data["message_id"],
            sender=AgentRole(data["sender"]),
            receiver=AgentRole(data["receiver"]),
            payload=data["payload"],
            task_description=data["task_description"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            parent_message_id=data.get("parent_message_id"),
        )


@dataclass
class AgentResponse:
    """
    Response from an agent after processing a message.
    
    Example:
        >>> response = AgentResponse(
        ...     message_id=msg.message_id,
        ...     status=MessageStatus.COMPLETED,
        ...     result={"spreadsheet_id": "abc123", "url": "https://..."},
        ...     agent=AgentRole.SHEETS
        ... )
    """
    
    message_id: str
    status: MessageStatus
    result: Dict[str, Any]
    agent: AgentRole
    response_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    next_agent: Optional[AgentRole] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for serialization."""
        return {
            "response_id": self.response_id,
            "message_id": self.message_id,
            "status": self.status.value,
            "result": self.result,
            "agent": self.agent.value,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "next_agent": self.next_agent.value if self.next_agent else None,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResponse":
        """Create response from dictionary."""
        return cls(
            response_id=data["response_id"],
            message_id=data["message_id"],
            status=MessageStatus(data["status"]),
            result=data["result"],
            agent=AgentRole(data["agent"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            error=data.get("error"),
            next_agent=AgentRole(data["next_agent"]) if data.get("next_agent") else None,
            metadata=data.get("metadata", {}),
        )


@dataclass
class WorkflowStep:
    """
    A single step in a multi-agent workflow.
    
    Example:
        >>> step1 = WorkflowStep(
        ...     agent=AgentRole.RESEARCH,
        ...     task_description="Research AI trends in 2026",
        ...     dependencies=[]
        ... )
        >>> step2 = WorkflowStep(
        ...     agent=AgentRole.SHEETS,
        ...     task_description="Create spreadsheet from research",
        ...     dependencies=[step1.step_id]
        ... )
    """
    
    agent: AgentRole
    task_description: str
    dependencies: List[str] = field(default_factory=list)
    step_id: str = field(default_factory=lambda: str(uuid4()))
    input_mapping: Dict[str, str] = field(default_factory=dict)
    error_handling: str = "stop"  # "stop" | "skip" | "retry"
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary."""
        return {
            "step_id": self.step_id,
            "agent": self.agent.value,
            "task_description": self.task_description,
            "dependencies": self.dependencies,
            "input_mapping": self.input_mapping,
            "error_handling": self.error_handling,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        """Create step from dictionary."""
        return cls(
            step_id=data["step_id"],
            agent=AgentRole(data["agent"]),
            task_description=data["task_description"],
            dependencies=data.get("dependencies", []),
            input_mapping=data.get("input_mapping", {}),
            error_handling=data.get("error_handling", "stop"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )


@dataclass
class WorkflowDefinition:
    """
    Definition of a multi-agent workflow.
    
    Example:
        >>> workflow = WorkflowDefinition(
        ...     name="Research to Spreadsheet",
        ...     description="Research a topic and create a spreadsheet",
        ...     steps=[step1, step2],
        ...     initial_inputs={"topic": "AI trends 2026"}
        ... )
    """
    
    name: str
    description: str
    steps: List[WorkflowStep]
    initial_inputs: Dict[str, Any] = field(default_factory=dict)
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "initial_inputs": self.initial_inputs,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        """Create workflow from dictionary."""
        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data["description"],
            steps=[WorkflowStep.from_dict(s) for s in data["steps"]],
            initial_inputs=data.get("initial_inputs", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WorkflowResult:
    """
    Result of workflow execution.
    
    Example:
        >>> result = WorkflowResult(
        ...     workflow_id=workflow.workflow_id,
        ...     status=MessageStatus.COMPLETED,
        ...     step_results={"step1": {...}, "step2": {...}},
        ...     final_output={"spreadsheet_id": "abc123"}
        ... )
    """
    
    workflow_id: str
    status: MessageStatus
    step_results: Dict[str, AgentResponse]
    final_output: Dict[str, Any]
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "final_output": self.final_output,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowResult":
        """Create result from dictionary."""
        return cls(
            execution_id=data["execution_id"],
            workflow_id=data["workflow_id"],
            status=MessageStatus(data["status"]),
            step_results={k: AgentResponse.from_dict(v) for k, v in data["step_results"].items()},
            final_output=data["final_output"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )
