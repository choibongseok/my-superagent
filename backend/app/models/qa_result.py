"""Quality Assurance Result model."""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class QAResult(Base, TimestampMixin):
    """Quality Assurance validation result for agent outputs."""
    
    __tablename__ = "qa_results"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    
    # Overall quality score (0-100)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Individual dimension scores
    grammar_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fact_check_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    structure_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Detailed results
    grammar_issues: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fact_check_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    structure_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    readability_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    missing_sections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Suggestions for improvement
    auto_fix_suggestions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Confidence scoring
    confidence_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Validation metadata
    validation_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    validator_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="qa_results")
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "overall_score": self.overall_score,
            "scores": {
                "grammar": self.grammar_score,
                "fact_check": self.fact_check_score,
                "structure": self.structure_score,
                "readability": self.readability_score,
                "completeness": self.completeness_score,
            },
            "details": {
                "grammar_issues": self.grammar_issues,
                "fact_check_results": self.fact_check_results,
                "structure_analysis": self.structure_analysis,
                "readability_metrics": self.readability_metrics,
                "missing_sections": self.missing_sections,
            },
            "suggestions": self.auto_fix_suggestions,
            "confidence": {
                "level": self.confidence_level,
                "score": self.confidence_score,
            },
            "metadata": {
                "validation_time_ms": self.validation_time_ms,
                "validator_version": self.validator_version,
                "created_at": self.created_at.isoformat() if self.created_at else None,
            },
        }
    
    def get_grade(self) -> str:
        """Get letter grade based on overall score."""
        if self.overall_score >= 90:
            return "A"
        elif self.overall_score >= 80:
            return "B"
        elif self.overall_score >= 70:
            return "C"
        elif self.overall_score >= 60:
            return "D"
        else:
            return "F"
    
    def needs_improvement(self) -> bool:
        """Check if output needs improvement (score < 70)."""
        return self.overall_score < 70.0
