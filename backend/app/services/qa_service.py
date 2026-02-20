"""Quality Assurance Service for validating agent outputs.

Provides multi-dimensional quality scoring:
- Grammar: spelling, punctuation, sentence structure
- Structure: headings, sections, logical flow
- Readability: Flesch-Kincaid, sentence length, complexity
- Completeness: required sections, prompt coverage
- Fact-check: citation verification, source quality

Idea #111 from the backlog.
"""

import logging
import re
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Text analysis helpers
# ---------------------------------------------------------------------------

def _count_syllables(word: str) -> int:
    """Estimate syllable count for an English word."""
    word = word.lower().strip()
    if not word:
        return 0
    # Simple heuristic
    count = 0
    vowels = "aeiouy"
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Adjust for silent-e
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch_reading_ease(text: str) -> float:
    """Calculate Flesch Reading Ease score (0-100, higher = easier)."""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    if not sentences or not words:
        return 50.0  # neutral default
    total_syllables = sum(_count_syllables(w) for w in words)
    asl = len(words) / len(sentences)  # average sentence length
    asw = total_syllables / len(words)  # average syllables per word
    score = 206.835 - 1.015 * asl - 84.6 * asw
    return max(0.0, min(100.0, score))


def _avg_sentence_length(text: str) -> float:
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r'\b\w+\b', text)
    if not sentences:
        return 0.0
    return len(words) / len(sentences)


# ---------------------------------------------------------------------------
# Individual dimension validators
# ---------------------------------------------------------------------------

def _check_grammar(text: str) -> Tuple[float, Dict]:
    """Check grammar quality.
    
    Returns (score 0-100, details dict).
    Lightweight heuristic approach (no external API dependency).
    """
    issues: List[Dict[str, str]] = []
    words = text.split()
    total_words = len(words)
    if total_words == 0:
        return 0.0, {"issues": [], "word_count": 0}

    # Check for repeated words
    for i in range(len(words) - 1):
        if words[i].lower() == words[i + 1].lower() and words[i].lower() not in {
            "the", "a", "an", "is", "was", "had", "that", "very",
        }:
            issues.append({
                "type": "repeated_word",
                "word": words[i],
                "position": i,
            })

    # Check for very long sentences (>40 words)
    sentences = re.split(r'[.!?]+', text)
    for idx, sent in enumerate(sentences):
        wc = len(sent.split())
        if wc > 40:
            issues.append({
                "type": "long_sentence",
                "sentence_index": idx,
                "word_count": wc,
            })

    # Check for missing capitalization after sentence-ending punctuation
    cap_pattern = re.compile(r'[.!?]\s+[a-z]')
    for m in cap_pattern.finditer(text):
        issues.append({
            "type": "capitalization",
            "position": m.start(),
            "snippet": m.group(),
        })

    # Check for double spaces
    double_spaces = len(re.findall(r'  +', text))
    if double_spaces:
        issues.append({
            "type": "double_spaces",
            "count": double_spaces,
        })

    # Score: deduct points per issue (max deduction capped)
    deduction = min(len(issues) * 5, 50)
    score = max(0.0, 100.0 - deduction)

    return score, {
        "issues": issues[:20],  # cap reported issues
        "issue_count": len(issues),
        "word_count": total_words,
    }


def _check_structure(text: str, task_type: Optional[str] = None) -> Tuple[float, Dict]:
    """Evaluate document structure (headings, sections, logical flow)."""
    lines = text.split('\n')
    headings = [l for l in lines if l.strip().startswith('#') or l.strip().startswith('**')]
    paragraphs = [l for l in lines if l.strip() and not l.strip().startswith('#')]
    bullet_points = [l for l in lines if l.strip().startswith(('-', '*', '•', '1.'))]

    has_title = bool(headings)
    section_count = len(headings)
    has_bullets = bool(bullet_points)
    total_lines = len([l for l in lines if l.strip()])

    analysis = {
        "heading_count": section_count,
        "paragraph_count": len(paragraphs),
        "bullet_point_count": len(bullet_points),
        "total_non_empty_lines": total_lines,
        "has_title": has_title,
    }

    # Scoring
    score = 50.0  # base

    if has_title:
        score += 15
    if section_count >= 2:
        score += 15
    elif section_count >= 1:
        score += 8
    if has_bullets:
        score += 10
    if total_lines >= 5:
        score += 10

    # Bonus for well-structured research output
    if task_type == "research":
        expected = {"introduction", "findings", "conclusion", "summary", "sources", "references"}
        lower_text = text.lower()
        matched = sum(1 for kw in expected if kw in lower_text)
        score += min(matched * 3, 10)

    return min(score, 100.0), analysis


def _check_readability(text: str) -> Tuple[float, Dict]:
    """Calculate readability metrics."""
    fre = _flesch_reading_ease(text)
    asl = _avg_sentence_length(text)
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    
    # Complex words (3+ syllables)
    complex_words = [w for w in words if _count_syllables(w) >= 3]
    complex_pct = (len(complex_words) / word_count * 100) if word_count else 0

    metrics = {
        "flesch_reading_ease": round(fre, 1),
        "avg_sentence_length": round(asl, 1),
        "word_count": word_count,
        "complex_word_count": len(complex_words),
        "complex_word_pct": round(complex_pct, 1),
    }

    # Map FRE to 0-100 quality score
    # FRE 60-70 is "standard" = good, very low or very high can be bad
    if fre >= 60:
        score = min(100, 60 + fre * 0.4)
    elif fre >= 30:
        score = 40 + fre * 0.5
    else:
        score = max(20, fre * 1.5)

    # Penalize extremely long average sentences
    if asl > 30:
        score -= 10
    elif asl > 25:
        score -= 5

    return max(0.0, min(100.0, score)), metrics


def _check_completeness(
    text: str,
    prompt: str,
    task_type: Optional[str] = None,
) -> Tuple[float, Dict]:
    """Check if the output adequately covers the prompt."""
    text_lower = text.lower()
    prompt_lower = prompt.lower()

    # Extract key terms from prompt (simple keyword extraction)
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "about", "as", "into", "through", "during", "before", "after",
        "and", "but", "or", "nor", "not", "so", "if", "then",
        "that", "this", "it", "my", "your", "their", "our", "its",
        "me", "i", "you", "he", "she", "we", "they", "what", "which",
        "who", "when", "where", "how", "why", "all", "each", "every",
        "create", "make", "write", "generate", "please", "help",
    }
    prompt_words = set(re.findall(r'\b[a-z]{3,}\b', prompt_lower))
    key_terms = prompt_words - stop_words

    if not key_terms:
        return 80.0, {"key_terms": [], "matched": [], "missing": [], "coverage_pct": 100}

    matched = [t for t in key_terms if t in text_lower]
    missing = [t for t in key_terms if t not in text_lower]
    coverage = len(matched) / len(key_terms) * 100

    # Length check
    word_count = len(text.split())
    length_ok = word_count >= 50  # minimum useful output

    missing_sections: List[str] = []
    # Task-type specific required sections
    if task_type == "research":
        for section in ["source", "reference", "finding", "conclusion"]:
            if section not in text_lower:
                missing_sections.append(section)
    elif task_type == "docs":
        for section in ["introduction", "content", "summary"]:
            if section not in text_lower:
                missing_sections.append(section)

    score = coverage
    if not length_ok:
        score -= 20
    if missing_sections:
        score -= len(missing_sections) * 5

    return max(0.0, min(100.0, score)), {
        "key_terms": sorted(key_terms),
        "matched": sorted(matched),
        "missing": sorted(missing),
        "coverage_pct": round(coverage, 1),
        "word_count": word_count,
        "min_word_count_met": length_ok,
        "missing_sections": missing_sections,
    }


def _check_citations(
    text: str,
    result_data: Optional[Dict] = None,
) -> Tuple[float, Dict]:
    """Check citation quality and source references."""
    # Extract URLs from text
    url_pattern = re.compile(r'https?://[^\s\)\"\']+')
    urls = url_pattern.findall(text)

    # Check for citation patterns: [1], (Author, Year), etc.
    numbered_refs = re.findall(r'\[\d+\]', text)
    author_refs = re.findall(r'\([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&\s+[A-Z][a-z]+))?,\s*\d{4}\)', text)

    # Check result data for citations
    result_citations = []
    if result_data and isinstance(result_data, dict):
        result_citations = result_data.get("citations", [])
        if not result_citations:
            result_citations = result_data.get("sources", [])

    total_refs = len(urls) + len(numbered_refs) + len(author_refs) + len(result_citations)

    analysis = {
        "url_count": len(urls),
        "urls": urls[:10],
        "numbered_references": len(numbered_refs),
        "author_references": len(author_refs),
        "result_citations": len(result_citations),
        "total_references": total_refs,
    }

    if total_refs == 0:
        return 30.0, analysis  # No citations at all
    elif total_refs <= 2:
        score = 50.0
    elif total_refs <= 5:
        score = 70.0
    else:
        score = 85.0

    # Bonus for diverse source types
    source_types = sum([
        1 if urls else 0,
        1 if numbered_refs else 0,
        1 if author_refs else 0,
        1 if result_citations else 0,
    ])
    if source_types >= 2:
        score += 10

    return min(100.0, score), analysis


# ---------------------------------------------------------------------------
# Main QA Service
# ---------------------------------------------------------------------------

class QAService:
    """Service for validating and scoring agent output quality."""

    def __init__(self):
        self.validator_version = VALIDATOR_VERSION

    def validate(
        self,
        text: str,
        prompt: str,
        task_type: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run full QA validation on agent output.

        Args:
            text: The agent's text output to validate.
            prompt: The original user prompt.
            task_type: Type of task (research, docs, sheets, slides).
            result_data: Raw result dict from the agent (may contain citations etc).

        Returns:
            Dict with scores, details, suggestions, and metadata.
        """
        start = datetime.now(timezone.utc)

        # Run all checks
        grammar_score, grammar_details = _check_grammar(text)
        structure_score, structure_details = _check_structure(text, task_type)
        readability_score, readability_metrics = _check_readability(text)
        completeness_score, completeness_details = _check_completeness(text, prompt, task_type)
        fact_score, fact_details = _check_citations(text, result_data)

        # Weighted overall score
        weights = {
            "grammar": 0.20,
            "structure": 0.20,
            "readability": 0.15,
            "completeness": 0.30,
            "fact_check": 0.15,
        }
        overall = (
            grammar_score * weights["grammar"]
            + structure_score * weights["structure"]
            + readability_score * weights["readability"]
            + completeness_score * weights["completeness"]
            + fact_score * weights["fact_check"]
        )

        # Confidence level
        if overall >= 85:
            confidence_level = "high"
        elif overall >= 65:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

        # Generate improvement suggestions
        suggestions = self._generate_suggestions(
            grammar_score, grammar_details,
            structure_score, structure_details,
            readability_score, readability_metrics,
            completeness_score, completeness_details,
            fact_score, fact_details,
        )

        return {
            "overall_score": round(overall, 1),
            "grade": self._letter_grade(overall),
            "scores": {
                "grammar": round(grammar_score, 1),
                "structure": round(structure_score, 1),
                "readability": round(readability_score, 1),
                "completeness": round(completeness_score, 1),
                "fact_check": round(fact_score, 1),
            },
            "details": {
                "grammar": grammar_details,
                "structure": structure_details,
                "readability": readability_metrics,
                "completeness": completeness_details,
                "fact_check": fact_details,
            },
            "suggestions": suggestions,
            "confidence": {
                "level": confidence_level,
                "score": round(overall / 100, 2),
            },
            "metadata": {
                "validation_time_ms": elapsed_ms,
                "validator_version": self.validator_version,
                "task_type": task_type,
            },
        }

    def validate_quick(self, text: str, prompt: str) -> Dict[str, Any]:
        """Fast validation returning only the overall score and grade."""
        result = self.validate(text, prompt)
        return {
            "overall_score": result["overall_score"],
            "grade": result["grade"],
            "confidence": result["confidence"]["level"],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _letter_grade(score: float) -> str:
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    @staticmethod
    def _generate_suggestions(
        grammar_score, grammar_details,
        structure_score, structure_details,
        readability_score, readability_metrics,
        completeness_score, completeness_details,
        fact_score, fact_details,
    ) -> List[Dict[str, str]]:
        suggestions: List[Dict[str, str]] = []

        if grammar_score < 70:
            issues = grammar_details.get("issues", [])
            if any(i["type"] == "long_sentence" for i in issues):
                suggestions.append({
                    "category": "grammar",
                    "priority": "high",
                    "suggestion": "Break long sentences (>40 words) into shorter ones for clarity.",
                })
            if any(i["type"] == "repeated_word" for i in issues):
                suggestions.append({
                    "category": "grammar",
                    "priority": "medium",
                    "suggestion": "Remove repeated consecutive words.",
                })
            if any(i["type"] == "capitalization" for i in issues):
                suggestions.append({
                    "category": "grammar",
                    "priority": "low",
                    "suggestion": "Capitalize the first word after sentence-ending punctuation.",
                })

        if structure_score < 70:
            if not structure_details.get("has_title"):
                suggestions.append({
                    "category": "structure",
                    "priority": "high",
                    "suggestion": "Add a clear title/heading at the beginning.",
                })
            if structure_details.get("heading_count", 0) < 2:
                suggestions.append({
                    "category": "structure",
                    "priority": "medium",
                    "suggestion": "Add section headings to improve organization.",
                })

        if readability_score < 60:
            fre = readability_metrics.get("flesch_reading_ease", 50)
            if fre < 30:
                suggestions.append({
                    "category": "readability",
                    "priority": "high",
                    "suggestion": "Simplify vocabulary and shorten sentences. Current readability is very low.",
                })
            asl = readability_metrics.get("avg_sentence_length", 0)
            if asl > 25:
                suggestions.append({
                    "category": "readability",
                    "priority": "medium",
                    "suggestion": f"Average sentence length is {asl:.0f} words — aim for 15-20.",
                })

        if completeness_score < 70:
            missing = completeness_details.get("missing", [])
            if missing:
                suggestions.append({
                    "category": "completeness",
                    "priority": "high",
                    "suggestion": f"Cover these key topics from the prompt: {', '.join(missing[:5])}",
                })
            missing_sections = completeness_details.get("missing_sections", [])
            if missing_sections:
                suggestions.append({
                    "category": "completeness",
                    "priority": "medium",
                    "suggestion": f"Add expected sections: {', '.join(missing_sections)}",
                })

        if fact_score < 60:
            if fact_details.get("total_references", 0) == 0:
                suggestions.append({
                    "category": "fact_check",
                    "priority": "high",
                    "suggestion": "Add source citations or references to support claims.",
                })
            elif fact_details.get("total_references", 0) < 3:
                suggestions.append({
                    "category": "fact_check",
                    "priority": "medium",
                    "suggestion": "Include more diverse sources (aim for 3+ references).",
                })

        return suggestions


# Module-level singleton
qa_service = QAService()
