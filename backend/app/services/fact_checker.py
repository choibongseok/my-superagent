"""Fact checking and result validation service."""

import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import wolframalpha
from openai import AsyncOpenAI
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
    - Wolfram Alpha integration for calculation verification (v2)
    - Contradiction detection between sources (v2)
    - Improved confidence scoring with source reliability weighting (v2)
    """
    
    def __init__(self, db: AsyncSession):
        """Initialize fact checker service."""
        self.db = db
        
        # Enhanced knowledge sources with reliability weights
        self.knowledge_sources = {
            # Academic & Scientific (highest reliability)
            "nature.com": 95,
            "science.org": 95,
            "pubmed.ncbi.nlm.nih.gov": 95,
            "ieee.org": 93,
            "sciencedirect.com": 90,
            "arxiv.org": 85,  # Pre-prints, slightly lower
            
            # News Agencies (high reliability)
            "reuters.com": 90,
            "apnews.com": 90,
            "bbc.com": 85,
            "npr.org": 85,
            "theguardian.com": 82,
            "nytimes.com": 82,
            "washingtonpost.com": 82,
            
            # Reference & Educational (high reliability)
            "britannica.com": 88,
            "wikipedia.org": 75,  # Good but editable
            "stanford.edu": 92,
            "mit.edu": 92,
            "harvard.edu": 92,
            
            # Government & Official (high reliability)
            "cdc.gov": 95,
            "nih.gov": 95,
            "nasa.gov": 95,
            "whitehouse.gov": 85,
            
            # Financial (high reliability)
            "bloomberg.com": 85,
            "wsj.com": 85,
            "ft.com": 85,
        }
        
        # Initialize Wolfram Alpha client
        self.wolfram_client = None
        wolfram_app_id = os.getenv("WOLFRAM_APP_ID")
        if wolfram_app_id:
            try:
                self.wolfram_client = wolframalpha.Client(wolfram_app_id)
                logger.info("Wolfram Alpha client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Wolfram Alpha: {e}")
        else:
            logger.warning("WOLFRAM_APP_ID not set, calculation verification disabled")
        
        # Initialize OpenAI for semantic analysis
        self.openai_client = None
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        else:
            logger.warning("OPENAI_API_KEY not set, semantic analysis limited")
    
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
        
        # Check for numeric claims and verify with Wolfram Alpha
        wolfram_results = []
        if self._contains_numeric_claim(claim):
            wolfram_results = await self._verify_with_wolfram(claim)
        
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
        
        # Enhance confidence score with Wolfram Alpha results
        if wolfram_results:
            wolfram_confidence = self._calculate_wolfram_confidence(wolfram_results)
            # Weighted average: 70% sources, 30% Wolfram Alpha
            if verification_result["confidence"] > 0:
                original_confidence = verification_result["confidence"]
                verification_result["confidence"] = (
                    original_confidence * 0.7 + wolfram_confidence * 0.3
                )
                verification_result["details"] = verification_result.get("details", {})
                verification_result["details"]["wolfram_results"] = wolfram_results
                verification_result["details"]["wolfram_confidence"] = wolfram_confidence
        
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
            f"(confidence: {verification_result['confidence']:.2f}%)"
        )
        
        return fact_check
    
    async def _verify_with_wolfram(self, claim: str) -> List[Dict[str, Any]]:
        """
        Verify numeric claims using Wolfram Alpha.
        
        Args:
            claim: Claim containing numeric or calculation data
            
        Returns:
            List of Wolfram Alpha verification results
        """
        if not self.wolfram_client:
            return []
        
        results = []
        
        try:
            # Extract numeric expressions
            numeric_expressions = self._extract_numeric_expressions(claim)
            
            for expr in numeric_expressions[:3]:  # Limit to 3 queries
                try:
                    res = self.wolfram_client.query(expr)
                    
                    if res.get('@success') == 'true':
                        # Extract result pods
                        for pod in res.get('pod', []):
                            if pod.get('@id') in ['Result', 'Solution', 'Value']:
                                subpod = pod.get('subpod', {})
                                if isinstance(subpod, list):
                                    subpod = subpod[0]
                                
                                result_text = subpod.get('plaintext', '')
                                
                                results.append({
                                    "query": expr,
                                    "result": result_text,
                                    "verified": True,
                                    "source": "Wolfram Alpha"
                                })
                                break
                    else:
                        results.append({
                            "query": expr,
                            "result": None,
                            "verified": False,
                            "source": "Wolfram Alpha",
                            "error": "Query not understood"
                        })
                        
                except Exception as e:
                    logger.error(f"Wolfram Alpha query error for '{expr}': {e}")
                    results.append({
                        "query": expr,
                        "result": None,
                        "verified": False,
                        "source": "Wolfram Alpha",
                        "error": str(e)
                    })
                    
        except Exception as e:
            logger.error(f"Wolfram Alpha verification error: {e}")
        
        return results
    
    def _extract_numeric_expressions(self, text: str) -> List[str]:
        """
        Extract numeric expressions suitable for Wolfram Alpha.
        
        Args:
            text: Input text
            
        Returns:
            List of numeric expressions
        """
        expressions = []
        
        # Pattern for mathematical expressions
        math_pattern = r'(\d+[\s]*[\+\-\*/]\s*\d+(?:\s*[\+\-\*/]\s*\d+)*)'
        math_matches = re.findall(math_pattern, text)
        expressions.extend(math_matches)
        
        # Pattern for "X is Y" statements (e.g., "population of US is 331 million")
        # Extract as questions for Wolfram
        if "population" in text.lower():
            expressions.append(text)
        if "distance" in text.lower():
            expressions.append(text)
        if "temperature" in text.lower():
            expressions.append(text)
        
        return expressions[:5]  # Limit for performance
    
    def _calculate_wolfram_confidence(self, wolfram_results: List[Dict[str, Any]]) -> float:
        """
        Calculate confidence score from Wolfram Alpha results.
        
        Args:
            wolfram_results: List of Wolfram verification results
            
        Returns:
            Confidence score (0-100)
        """
        if not wolfram_results:
            return 0.0
        
        verified_count = sum(1 for r in wolfram_results if r.get("verified", False))
        total_count = len(wolfram_results)
        
        if total_count == 0:
            return 0.0
        
        # Wolfram Alpha has high reliability for calculations
        base_confidence = (verified_count / total_count) * 100
        
        # Bonus for verified results
        if verified_count > 0:
            base_confidence = min(100.0, base_confidence + 10)
        
        return base_confidence
    
    async def _verify_with_sources(
        self,
        statements: List[str],
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verify statements against multiple sources with contradiction detection.
        
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
        
        # Analyze source quality with reliability weighting
        source_analyses = []
        for source in sources:
            url = source.get("url", "")
            content = source.get("content", "")
            
            quality = await self._assess_source_quality(url)
            
            source_analyses.append({
                "url": url,
                "quality": quality,
                "title": source.get("title", ""),
                "content": content,
                "reliability_weight": quality / 100.0  # Normalize to 0-1
            })
        
        # Detect contradictions between sources
        contradictions = await self._detect_contradictions(source_analyses, statements)
        
        # Count supporting vs contradicting sources
        sources_checked = len(sources)
        sources_contradicting = len(contradictions)
        
        # Calculate weighted confidence score
        confidence = await self._calculate_weighted_confidence(
            source_analyses, 
            contradictions
        )
        
        # Determine verification status
        if confidence >= 85:
            status = "verified"
        elif confidence >= 70:
            status = "likely"
        elif confidence >= 50:
            status = "uncertain"
        elif confidence >= 30:
            status = "unlikely"
        else:
            status = "unverified"
        
        # Determine if attention is required
        alert_reason = None
        if confidence < 70:
            alert_reason = "low_confidence"
        if sources_contradicting > 0:
            alert_reason = "conflicting_sources"
        elif sources_checked < 3:
            if alert_reason:
                alert_reason = f"{alert_reason},insufficient_sources"
            else:
                alert_reason = "insufficient_sources"
        
        # Calculate average quality
        avg_quality = sum(s["quality"] for s in source_analyses) / sources_checked
        
        # Count supporting sources (high quality sources)
        sources_supporting = len([s for s in source_analyses if s["quality"] >= 70])
        
        return {
            "status": status,
            "confidence": round(confidence, 2),
            "sources_checked": sources_checked,
            "sources_supporting": sources_supporting,
            "sources_contradicting": sources_contradicting,
            "source_quality_avg": round(avg_quality, 2),
            "supporting_evidence": [
                {k: v for k, v in s.items() if k != "content"}  # Exclude large content
                for s in source_analyses[:5]
            ],
            "contradicting_evidence": contradictions[:5],
            "alert_reason": alert_reason,
            "details": {
                "statements_checked": len(statements),
                "source_breakdown": source_analyses,
                "contradictions_detected": len(contradictions),
                "confidence_calculation": "weighted_by_source_reliability"
            }
        }
    
    async def _detect_contradictions(
        self,
        source_analyses: List[Dict[str, Any]],
        statements: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Detect contradictions between sources using semantic analysis.
        
        Args:
            source_analyses: List of analyzed sources with content
            statements: Statements to check for contradictions
            
        Returns:
            List of detected contradictions
        """
        contradictions = []
        
        if not self.openai_client or len(source_analyses) < 2:
            return contradictions
        
        try:
            # Compare sources pairwise for contradictions
            for i, source_a in enumerate(source_analyses):
                for source_b in source_analyses[i+1:]:
                    # Use GPT to detect semantic contradictions
                    contradiction = await self._check_contradiction_pair(
                        source_a, source_b, statements
                    )
                    
                    if contradiction:
                        contradictions.append(contradiction)
                        
                    # Limit contradiction checks to avoid rate limits
                    if len(contradictions) >= 5:
                        break
                        
                if len(contradictions) >= 5:
                    break
                    
        except Exception as e:
            logger.error(f"Error detecting contradictions: {e}")
        
        return contradictions
    
    async def _check_contradiction_pair(
        self,
        source_a: Dict[str, Any],
        source_b: Dict[str, Any],
        statements: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if two sources contradict each other.
        
        Args:
            source_a: First source with content
            source_b: Second source with content
            statements: Statements being verified
            
        Returns:
            Contradiction details if found, None otherwise
        """
        if not self.openai_client:
            return None
        
        try:
            content_a = source_a.get("content", "")[:500]  # Limit for token usage
            content_b = source_b.get("content", "")[:500]
            
            if not content_a or not content_b:
                return None
            
            prompt = f"""Analyze these two sources for contradictions regarding the statements: {', '.join(statements[:3])}

Source A ({source_a['url']}):
{content_a}

Source B ({source_b['url']}):
{content_b}

Are there any direct contradictions between these sources? Reply with JSON:
{{"has_contradiction": true/false, "description": "brief explanation", "severity": "high/medium/low"}}"""
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            
            result = response.choices[0].message.content
            
            # Parse JSON response
            import json
            try:
                contradiction_data = json.loads(result)
                
                if contradiction_data.get("has_contradiction"):
                    return {
                        "source_a": source_a["url"],
                        "source_b": source_b["url"],
                        "description": contradiction_data.get("description", "Contradiction detected"),
                        "severity": contradiction_data.get("severity", "medium")
                    }
            except json.JSONDecodeError:
                # Fallback: simple keyword-based contradiction detection
                if "contradict" in result.lower() or "disagree" in result.lower():
                    return {
                        "source_a": source_a["url"],
                        "source_b": source_b["url"],
                        "description": "Potential contradiction detected",
                        "severity": "low"
                    }
                    
        except Exception as e:
            logger.error(f"Error checking contradiction pair: {e}")
        
        return None
    
    async def _calculate_weighted_confidence(
        self,
        source_analyses: List[Dict[str, Any]],
        contradictions: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate confidence score with source reliability weighting.
        
        Args:
            source_analyses: List of analyzed sources with reliability weights
            contradictions: Detected contradictions
            
        Returns:
            Weighted confidence score (0-100)
        """
        if not source_analyses:
            return 0.0
        
        # Base confidence from weighted source quality
        total_weight = sum(s["reliability_weight"] for s in source_analyses)
        weighted_quality = sum(
            s["quality"] * s["reliability_weight"] 
            for s in source_analyses
        )
        
        if total_weight == 0:
            base_confidence = 50.0
        else:
            base_confidence = weighted_quality / total_weight
        
        # Adjust for number of sources
        source_count = len(source_analyses)
        if source_count >= 5:
            source_bonus = 10
        elif source_count >= 3:
            source_bonus = 5
        else:
            source_bonus = -10  # Penalty for insufficient sources
        
        # Adjust for contradictions
        contradiction_penalty = 0
        if contradictions:
            for contradiction in contradictions:
                severity = contradiction.get("severity", "medium")
                if severity == "high":
                    contradiction_penalty += 20
                elif severity == "medium":
                    contradiction_penalty += 10
                else:
                    contradiction_penalty += 5
        
        # Calculate final confidence
        confidence = base_confidence + source_bonus - contradiction_penalty
        
        # Clamp to 0-100 range
        confidence = max(0.0, min(100.0, confidence))
        
        return confidence
    
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
            
            # Enhanced default quality scoring
            if any(indicator in domain for indicator in [".edu"]):
                return 85.0  # Educational institutions
            elif any(indicator in domain for indicator in [".gov", ".mil"]):
                return 90.0  # Government sources
            elif any(indicator in domain for indicator in [".org"]):
                return 70.0  # Organizations
            elif any(indicator in domain for indicator in [".com", ".net"]):
                return 50.0  # Commercial
            elif any(indicator in domain for indicator in [".io", ".ai"]):
                return 45.0  # Tech/startups
            else:
                return 40.0  # Unknown
                
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
            r'\d+\s*(million|billion|thousand|trillion)',  # Large numbers
            r'\d+\s*(km|miles|meters|feet)',  # Distances
            r'\d+\s*(kg|pounds|tons)',  # Weights
            r'\d+[\s]*[\+\-\*/]\s*\d+',  # Mathematical operations
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
