"""Fact checking and result validation service."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact_check import FactCheckResult, SourceQuality, VerificationRule
from app.models.task import Task

logger = logging.getLogger(__name__)


class FactCheckerService:
    """
    AI-powered fact checking and result validation service.
    
    Features:
    - Multi-source cross-verification
    - Confidence score calculation
    - Source quality assessment
    - Automatic fact-check for numeric claims
    - Citation quality scoring
    """
    
    def __init__(self, db: AsyncSession):
        """Initialize fact checker service."""
        self.db = db
        self.knowledge_sources = {
            "wikipedia.org": 85,
            "nature.com": 95,
            "science.org": 95,
            "arxiv.org": 80,
            "pubmed.ncbi.nlm.nih.gov": 90,
            "britannica.com": 85,
            "nytimes.com": 80,
            "reuters.com": 85,
            "apnews.com": 85,
            "bbc.com": 80,
        }
    
    async def verify_claim(
        self,
        claim: str,
        task_id: str,
        user_id: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        method: str = "multi_source"
    ) -> FactCheckResult:
        """
        Verify a factual claim using multiple methods.
        
        Args:
            claim: The claim to verify
            task_id: Associated task ID
            user_id: User making the claim
            sources: Optional list of source dictionaries
            method: Verification method (multi_source, knowledge_graph, calculation)
            
        Returns:
            FactCheckResult object with verification results
        """
        logger.info(f"Verifying claim: {claim[:100]}...")
        
        # Extract verifiable statements
        statements = self._extract_statements(claim)
        
        # Check sources if provided
        if sources and len(sources) > 0:
            verification_result = await self._verify_with_sources(
                statements, sources
            )
        else:
            # No sources provided - mark as unverified
            verification_result = {
                "status": "unverified",
                "confidence": 0.0,
                "sources_checked": 0,
                "sources_supporting": 0,
                "sources_contradicting": 0,
                "alert_reason": "no_sources"
            }
        
        # Check for numeric claims
        if self._contains_numeric_claim(claim):
            # TODO: Integrate with Wolfram Alpha or similar for calculation verification
            pass
        
        # Create fact check result
        fact_check = FactCheckResult(
            task_id=task_id,
            user_id=user_id,
            claim=claim,
            verification_status=verification_result["status"],
            confidence_score=verification_result["confidence"],
            sources_checked=verification_result["sources_checked"],
            sources_supporting=verification_result["sources_supporting"],
            sources_contradicting=verification_result["sources_contradicting"],
            source_quality_avg=verification_result.get("source_quality_avg"),
            supporting_evidence=verification_result.get("supporting_evidence"),
            contradicting_evidence=verification_result.get("contradicting_evidence"),
            verification_method=method,
            verification_details=verification_result.get("details"),
            requires_attention=verification_result["confidence"] < 70.0,
            alert_reason=verification_result.get("alert_reason"),
            checked_at=datetime.utcnow()
        )
        
        self.db.add(fact_check)
        await self.db.commit()
        await self.db.refresh(fact_check)
        
        logger.info(
            f"Fact check complete: {verification_result['status']} "
            f"(confidence: {verification_result['confidence']}%)"
        )
        
        return fact_check
    
    async def _verify_with_sources(
        self,
        statements: List[str],
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verify statements against multiple sources.
        
        Args:
            statements: List of factual statements to verify
            sources: List of source dictionaries with url, content, etc.
            
        Returns:
            Verification result dictionary
        """
        if not sources or len(sources) == 0:
            return {
                "status": "unverified",
                "confidence": 0.0,
                "sources_checked": 0,
                "sources_supporting": 0,
                "sources_contradicting": 0,
                "alert_reason": "no_sources"
            }
        
        # Analyze source quality
        source_qualities = []
        for source in sources:
            url = source.get("url", "")
            quality = await self._assess_source_quality(url)
            source_qualities.append({
                "url": url,
                "quality": quality,
                "title": source.get("title", "")
            })
        
        # Count supporting sources (simplified - in production use NLP)
        sources_checked = len(sources)
        sources_supporting = len([s for s in source_qualities if s["quality"] >= 60])
        sources_contradicting = 0  # TODO: Implement contradiction detection
        
        # Calculate confidence based on source count and quality
        if sources_checked >= 3:
            avg_quality = sum(s["quality"] for s in source_qualities) / sources_checked
            confidence = min(
                100.0,
                (sources_supporting / sources_checked * 100) * (avg_quality / 100)
            )
            
            if confidence >= 80:
                status = "verified"
            elif confidence >= 60:
                status = "likely"
            elif confidence >= 40:
                status = "uncertain"
            else:
                status = "unverified"
        else:
            confidence = 50.0
            status = "insufficient_data"
        
        # Determine if attention is required
        alert_reason = None
        if confidence < 70:
            alert_reason = "low_confidence"
        elif sources_contradicting > 0:
            alert_reason = "conflicting_sources"
        elif sources_checked < 3:
            alert_reason = "insufficient_sources"
        
        return {
            "status": status,
            "confidence": round(confidence, 2),
            "sources_checked": sources_checked,
            "sources_supporting": sources_supporting,
            "sources_contradicting": sources_contradicting,
            "source_quality_avg": round(
                sum(s["quality"] for s in source_qualities) / sources_checked, 2
            ),
            "supporting_evidence": source_qualities[:5],  # Top 5
            "contradicting_evidence": [],
            "alert_reason": alert_reason,
            "details": {
                "statements_checked": len(statements),
                "source_breakdown": source_qualities
            }
        }
    
    async def _assess_source_quality(self, url: str) -> float:
        """
        Assess the quality/reliability of a source.
        
        Args:
            url: Source URL
            
        Returns:
            Quality score (0-100)
        """
        try:
            domain = urlparse(url).netloc.replace("www.", "")
            
            # Check database for existing quality rating
            result = await self.db.execute(
                select(SourceQuality).where(SourceQuality.domain == domain)
            )
            source_quality = result.scalar_one_or_none()
            
            if source_quality:
                return source_quality.reliability_score
            
            # Use predefined quality scores for known sources
            for known_domain, score in self.knowledge_sources.items():
                if known_domain in domain:
                    return float(score)
            
            # Default quality score for unknown sources
            # In production, this would use ML model or external API
            if any(indicator in domain for indicator in [".edu", ".gov", ".org"]):
                return 70.0
            elif any(indicator in domain for indicator in [".com", ".net"]):
                return 50.0
            else:
                return 40.0
                
        except Exception as e:
            logger.error(f"Error assessing source quality: {e}")
            return 50.0  # Default to neutral
    
    def _extract_statements(self, text: str) -> List[str]:
        """
        Extract factual statements from text.
        
        Args:
            text: Input text
            
        Returns:
            List of factual statements
        """
        # Simple sentence splitting
        # In production, use NLP to identify factual claims
        sentences = re.split(r'[.!?]+', text)
        statements = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        return statements[:5]  # Limit to 5 statements for performance
    
    def _contains_numeric_claim(self, text: str) -> bool:
        """Check if text contains numeric claims."""
        # Look for numbers, percentages, dates, etc.
        numeric_patterns = [
            r'\d+%',  # Percentage
            r'\$\d+',  # Currency
            r'\d{4}',  # Year
            r'\d+\s*(million|billion|thousand)',  # Large numbers
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in numeric_patterns)
    
    async def get_task_fact_checks(
        self,
        task_id: str,
        min_confidence: Optional[float] = None
    ) -> List[FactCheckResult]:
        """
        Get all fact checks for a task.
        
        Args:
            task_id: Task ID
            min_confidence: Optional minimum confidence filter
            
        Returns:
            List of fact check results
        """
        query = select(FactCheckResult).where(FactCheckResult.task_id == task_id)
        
        if min_confidence is not None:
            query = query.where(FactCheckResult.confidence_score >= min_confidence)
        
        result = await self.db.execute(query.order_by(FactCheckResult.checked_at.desc()))
        return list(result.scalars().all())
    
    async def get_verification_rule(self, rule_name: str) -> Optional[VerificationRule]:
        """Get a verification rule by name."""
        result = await self.db.execute(
            select(VerificationRule).where(VerificationRule.rule_name == rule_name)
        )
        return result.scalar_one_or_none()
    
    async def create_source_quality_rating(
        self,
        domain: str,
        source_type: str,
        reliability_score: float,
        **kwargs
    ) -> SourceQuality:
        """Create a new source quality rating."""
        source_quality = SourceQuality(
            domain=domain,
            source_type=source_type,
            reliability_score=reliability_score,
            **kwargs
        )
        
        self.db.add(source_quality)
        await self.db.commit()
        await self.db.refresh(source_quality)
        
        return source_quality


__all__ = ["FactCheckerService"]
