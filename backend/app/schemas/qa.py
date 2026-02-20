"""Quality Assurance schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QAScores(BaseModel):
    """Individual dimension scores."""
    grammar: float
    structure: float
    readability: float
    completeness: float
    fact_check: float


class QAConfidence(BaseModel):
    """Confidence assessment."""
    level: str  # high, medium, low
    score: float  # 0.0 - 1.0


class QASuggestion(BaseModel):
    """Improvement suggestion."""
    category: str
    priority: str  # high, medium, low
    suggestion: str


class QAValidationRequest(BaseModel):
    """Request body for ad-hoc QA validation."""
    text: str = Field(..., min_length=1, max_length=100_000)
    prompt: str = Field(..., min_length=1, max_length=5000)
    task_type: Optional[str] = None


class QAValidationResponse(BaseModel):
    """Full QA validation response."""
    overall_score: float
    grade: str
    scores: QAScores
    suggestions: List[QASuggestion] = []
    confidence: QAConfidence
    metadata: Dict[str, Any] = {}


class QAQuickResponse(BaseModel):
    """Lightweight QA quick-check response."""
    overall_score: float
    grade: str
    confidence: str


class QAResultResponse(BaseModel):
    """QA result as stored in the database."""
    id: UUID
    task_id: UUID
    overall_score: float
    grade: str
    scores: QAScores
    suggestions: List[QASuggestion] = []
    confidence: QAConfidence
    metadata: Dict[str, Any] = {}
    created_at: datetime

    model_config = {"from_attributes": True}


class QAResultListResponse(BaseModel):
    """List of QA results."""
    results: List[QAResultResponse]
    total: int
