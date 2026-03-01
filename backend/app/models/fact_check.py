"""Fact checking and result validation models."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class FactCheckResult(Base):
    """
    Fact-check result for Agent outputs.
    
    Stores verification results, confidence scores, and source validations.
    """
    __tablename__ = "fact_check_results"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Verification details
    claim = Column(Text, nullable=False)  # The claim being verified
    verification_status = Column(String, nullable=False)  # verified, unverified, conflicting, insufficient_data
    confidence_score = Column(Float, nullable=False)  # 0-100
    
    # Source analysis
    sources_checked = Column(Integer, nullable=False, default=0)
    sources_supporting = Column(Integer, nullable=False, default=0)
    sources_contradicting = Column(Integer, nullable=False, default=0)
    source_quality_avg = Column(Float, nullable=True)  # Average source quality score
    
    # Evidence
    supporting_evidence = Column(JSON, nullable=True)  # List of supporting sources
    contradicting_evidence = Column(JSON, nullable=True)  # List of contradicting sources
    
    # Verification method
    verification_method = Column(String, nullable=False)  # multi_source, knowledge_graph, calculation, expert_system
    verification_details = Column(JSON, nullable=True)  # Additional details about verification
    
    # Alerts
    requires_attention = Column(Boolean, nullable=False, default=False)
    alert_reason = Column(String, nullable=True)  # low_confidence, conflicting_sources, no_sources
    
    # Metadata
    checked_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="fact_checks")
    user = relationship("User")
    
    def __repr__(self):
        return f"<FactCheckResult(claim={self.claim[:50]}..., confidence={self.confidence_score}%)>"


class SourceQuality(Base):
    """
    Source quality ratings for fact-checking.
    
    Tracks the reliability of different information sources.
    """
    __tablename__ = "source_quality"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Source identification
    domain = Column(String, nullable=False, unique=True, index=True)
    source_type = Column(String, nullable=False)  # academic, news, blog, social, official, other
    
    # Quality metrics
    reliability_score = Column(Float, nullable=False)  # 0-100
    bias_score = Column(Float, nullable=True)  # -100 (left) to +100 (right)
    factual_accuracy = Column(Float, nullable=True)  # Historical accuracy rate 0-100
    
    # Reputation
    citations_count = Column(Integer, nullable=False, default=0)
    verified_facts = Column(Integer, nullable=False, default=0)
    false_claims = Column(Integer, nullable=False, default=0)
    
    # Metadata
    last_updated = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<SourceQuality(domain={self.domain}, reliability={self.reliability_score})>"


class VerificationRule(Base):
    """
    Verification rules and thresholds.
    
    Defines when fact-checking should be triggered and what thresholds to use.
    """
    __tablename__ = "verification_rules"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Rule definition
    rule_name = Column(String, nullable=False, unique=True)
    rule_type = Column(String, nullable=False)  # claim_type, task_type, user_tier
    
    # Thresholds
    min_confidence_threshold = Column(Float, nullable=False, default=70.0)
    min_sources_required = Column(Integer, nullable=False, default=3)
    min_source_quality = Column(Float, nullable=False, default=60.0)
    
    # Behavior
    auto_verify = Column(Boolean, nullable=False, default=True)
    alert_on_low_confidence = Column(Boolean, nullable=False, default=True)
    block_on_contradiction = Column(Boolean, nullable=False, default=False)
    
    # Configuration
    enabled = Column(Boolean, nullable=False, default=True)
    rule_config = Column(JSON, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<VerificationRule(name={self.rule_name}, enabled={self.enabled})>"
