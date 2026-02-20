"""Tests for QA Service — multi-dimensional quality validation."""

import pytest
from app.services.qa_service import (
    QAService,
    qa_service,
    _count_syllables,
    _flesch_reading_ease,
    _check_grammar,
    _check_structure,
    _check_readability,
    _check_completeness,
    _check_citations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestSyllableCount:
    def test_single_syllable(self):
        assert _count_syllables("cat") == 1
        assert _count_syllables("the") == 1

    def test_multi_syllable(self):
        assert _count_syllables("banana") >= 2
        assert _count_syllables("information") >= 3

    def test_empty(self):
        assert _count_syllables("") == 0

    def test_silent_e(self):
        # "cake" should be 1 syllable
        assert _count_syllables("cake") == 1


class TestFleschReadingEase:
    def test_empty_text(self):
        assert _flesch_reading_ease("") == 50.0

    def test_simple_text(self):
        score = _flesch_reading_ease("The cat sat on the mat. It was a good day.")
        assert 0 <= score <= 100

    def test_complex_text(self):
        complex_text = (
            "The implementation of the aforementioned methodological "
            "framework necessitates comprehensive understanding of "
            "multidisciplinary theoretical perspectives."
        )
        score = _flesch_reading_ease(complex_text)
        assert score < 50  # complex text should score lower


# ---------------------------------------------------------------------------
# Grammar checks
# ---------------------------------------------------------------------------

class TestGrammarCheck:
    def test_clean_text(self):
        score, details = _check_grammar("This is a clean sentence. Another one here.")
        assert score >= 80
        assert details["issue_count"] == 0

    def test_repeated_words(self):
        score, details = _check_grammar("The the cat sat on on the mat.")
        assert score < 100
        assert any(i["type"] == "repeated_word" for i in details["issues"])

    def test_long_sentence(self):
        # Need actual words (>40) between sentence-ending punctuation
        long = "This is a very long sentence that just " + " ".join(["keeps going and"] * 12) + " never stops. Short one."
        score, details = _check_grammar(long)
        assert any(i["type"] == "long_sentence" for i in details["issues"])

    def test_capitalization(self):
        text = "First sentence. second sentence."
        score, details = _check_grammar(text)
        assert any(i["type"] == "capitalization" for i in details["issues"])

    def test_double_spaces(self):
        text = "Hello  world.  This has  extra spaces."
        score, details = _check_grammar(text)
        assert any(i["type"] == "double_spaces" for i in details["issues"])

    def test_empty_text(self):
        score, details = _check_grammar("")
        assert score == 0
        assert details["word_count"] == 0


# ---------------------------------------------------------------------------
# Structure checks
# ---------------------------------------------------------------------------

class TestStructureCheck:
    def test_well_structured(self):
        text = """# Title

## Introduction
Some intro text here.

## Findings
- Point one
- Point two
- Point three

## Conclusion
Final thoughts."""
        score, details = _check_structure(text)
        assert score >= 80
        assert details["has_title"]
        assert details["heading_count"] >= 3
        assert details["bullet_point_count"] >= 3

    def test_no_structure(self):
        text = "Just a plain paragraph with no headings or structure at all."
        score, details = _check_structure(text)
        assert score < 70
        assert not details["has_title"]

    def test_research_bonus(self):
        text = """# Research Report

## Introduction
Overview of findings.

## Findings
Key results here.

## Conclusion
Summary of work.

## References
Sources listed here."""
        score, _ = _check_structure(text, task_type="research")
        score_plain, _ = _check_structure(text, task_type=None)
        assert score >= score_plain  # research keywords give bonus


# ---------------------------------------------------------------------------
# Readability checks
# ---------------------------------------------------------------------------

class TestReadabilityCheck:
    def test_simple_text(self):
        score, metrics = _check_readability("The cat sat on the mat. It was happy.")
        assert score >= 50
        assert "flesch_reading_ease" in metrics
        assert "avg_sentence_length" in metrics
        assert "word_count" in metrics

    def test_complex_text(self):
        text = (
            "Notwithstanding the aforementioned considerations, the "
            "implementation of multifaceted organizational restructuring "
            "necessitates a comprehensive evaluation of interdepartmental "
            "synergies and the subsequent rationalization of redundant "
            "operational methodologies within the overarching strategic framework."
        )
        score, metrics = _check_readability(text)
        # Very complex = lower readability score
        assert metrics["complex_word_count"] > 3

    def test_empty_text(self):
        score, metrics = _check_readability("")
        assert metrics["word_count"] == 0


# ---------------------------------------------------------------------------
# Completeness checks
# ---------------------------------------------------------------------------

class TestCompletenessCheck:
    def test_good_coverage(self):
        prompt = "Write a report about artificial intelligence trends in 2026"
        text = (
            "Artificial intelligence continues to evolve rapidly in 2026. "
            "Key trends include large language models, autonomous agents, "
            "and multimodal AI. The report covers recent developments and "
            "future predictions for the intelligence sector."
        )
        score, details = _check_completeness(text, prompt)
        assert score >= 60
        assert details["coverage_pct"] >= 50

    def test_poor_coverage(self):
        prompt = "Analyze the economic impact of climate change on agriculture"
        text = "The weather has been interesting lately."
        score, details = _check_completeness(text, prompt)
        assert score < 60
        assert len(details["missing"]) > 0

    def test_short_output(self):
        prompt = "Write a detailed report"
        text = "Here is a brief note."
        score, details = _check_completeness(text, prompt)
        assert not details["min_word_count_met"]

    def test_research_missing_sections(self):
        prompt = "Research AI ethics"
        text = "AI ethics is important. We should think about it carefully."
        score, details = _check_completeness(text, prompt, task_type="research")
        assert len(details["missing_sections"]) > 0


# ---------------------------------------------------------------------------
# Citation checks
# ---------------------------------------------------------------------------

class TestCitationCheck:
    def test_no_citations(self):
        score, details = _check_citations("Just plain text with no references.")
        assert score <= 40
        assert details["total_references"] == 0

    def test_url_citations(self):
        text = (
            "According to research (https://example.com/study), "
            "AI is growing. See also https://arxiv.org/paper123."
        )
        score, details = _check_citations(text)
        assert score >= 50
        assert details["url_count"] >= 2

    def test_numbered_refs(self):
        text = "Studies show [1] that AI is evolving [2] rapidly [3]."
        score, details = _check_citations(text)
        assert details["numbered_references"] >= 3

    def test_author_refs(self):
        text = "According to (Smith, 2024) and (Johnson et al., 2025)."
        score, details = _check_citations(text)
        assert details["author_references"] >= 2

    def test_result_citations(self):
        text = "Some text here."
        result_data = {
            "citations": [
                {"url": "https://example.com", "title": "Source 1"},
                {"url": "https://example2.com", "title": "Source 2"},
            ]
        }
        score, details = _check_citations(text, result_data)
        assert details["result_citations"] >= 2

    def test_diverse_sources_bonus(self):
        text = (
            "Per [1] at https://example.com, "
            "and (Smith, 2024) confirms this."
        )
        score_diverse, details_diverse = _check_citations(text)
        text_single = "See [1] for details."
        score_single, _ = _check_citations(text_single)
        assert score_diverse >= score_single


# ---------------------------------------------------------------------------
# Full QA Service
# ---------------------------------------------------------------------------

class TestQAService:
    def setup_method(self):
        self.svc = QAService()

    def test_validate_returns_all_fields(self):
        result = self.svc.validate(
            text="# Report\n\nThis is a well-written report about AI.",
            prompt="Write a report about AI",
        )
        assert "overall_score" in result
        assert "grade" in result
        assert "scores" in result
        assert "details" in result
        assert "suggestions" in result
        assert "confidence" in result
        assert "metadata" in result
        assert result["metadata"]["validator_version"] == "1.0.0"

    def test_validate_score_range(self):
        result = self.svc.validate(
            text="# AI Report\n\n## Introduction\nAI is evolving.\n\n## Findings\n- Trend 1\n- Trend 2",
            prompt="Write about AI trends",
        )
        assert 0 <= result["overall_score"] <= 100
        for key, val in result["scores"].items():
            assert 0 <= val <= 100, f"{key} score out of range: {val}"

    def test_validate_with_task_type(self):
        text = """# Research on AI Ethics

## Introduction
Overview of AI ethics research.

## Findings
Key findings from recent studies [1].

## Conclusion
AI ethics requires ongoing attention.

## References
[1] https://example.com/ai-ethics
"""
        result = self.svc.validate(
            text=text,
            prompt="Research AI ethics",
            task_type="research",
        )
        assert result["overall_score"] >= 50
        assert result["grade"] in ("A", "B", "C", "D", "F")

    def test_validate_poor_output(self):
        result = self.svc.validate(
            text="ok",
            prompt="Write a comprehensive analysis of global economic trends",
        )
        assert result["overall_score"] < 60
        assert len(result["suggestions"]) > 0

    def test_validate_quick(self):
        result = self.svc.validate_quick(
            text="Some text about technology.",
            prompt="Write about technology",
        )
        assert "overall_score" in result
        assert "grade" in result
        assert "confidence" in result

    def test_grade_mapping(self):
        assert self.svc._letter_grade(95) == "A"
        assert self.svc._letter_grade(85) == "B"
        assert self.svc._letter_grade(75) == "C"
        assert self.svc._letter_grade(65) == "D"
        assert self.svc._letter_grade(55) == "F"

    def test_suggestions_for_poor_grammar(self):
        long_sentence = " ".join(["word"] * 50) + ". another sentence."
        result = self.svc.validate(text=long_sentence, prompt="test")
        grammar_suggestions = [s for s in result["suggestions"] if s["category"] == "grammar"]
        assert len(grammar_suggestions) > 0

    def test_suggestions_for_no_citations(self):
        text = "AI is growing rapidly worldwide with many applications."
        result = self.svc.validate(
            text=text,
            prompt="Research AI growth",
            task_type="research",
        )
        fact_suggestions = [s for s in result["suggestions"] if s["category"] == "fact_check"]
        assert len(fact_suggestions) > 0

    def test_high_quality_output(self):
        text = """# Comprehensive AI Trends Report 2026

## Introduction
This report analyzes the latest artificial intelligence trends shaping 
technology and business in 2026. Based on extensive research from multiple 
sources, we present key findings and actionable insights.

## Key Findings

### 1. Large Language Models
Large language models continue to improve, with capabilities expanding 
across reasoning, coding, and creative tasks. Companies are integrating 
these models into core business processes.

### 2. Autonomous Agents
AI agents capable of executing multi-step tasks autonomously are becoming 
mainstream. These agents can research topics, create documents, and manage 
workflows with minimal human intervention.

### 3. Multimodal AI
Models that process text, images, audio, and video simultaneously are 
enabling new applications in healthcare, education, and entertainment.

## Conclusion
The AI landscape in 2026 shows continued rapid evolution. Organizations 
must adapt their strategies to leverage these emerging capabilities while 
managing associated risks.

## References
[1] https://example.com/ai-trends-2026
[2] https://arxiv.org/paper/ai-agents
(Smith et al., 2026) "The State of AI", Annual Review of Technology
"""
        result = self.svc.validate(
            text=text,
            prompt="Write a report about AI trends in 2026",
            task_type="research",
        )
        assert result["overall_score"] >= 70
        assert result["confidence"]["level"] in ("high", "medium")

    def test_result_data_citations(self):
        text = "AI is transforming industries."
        result = self.svc.validate(
            text=text,
            prompt="Research AI",
            result_data={
                "citations": [
                    {"url": "https://example.com", "title": "AI Study"},
                    {"url": "https://research.org", "title": "ML Paper"},
                    {"url": "https://data.org", "title": "Data Report"},
                ]
            },
        )
        fact_score = result["scores"]["fact_check"]
        assert fact_score >= 50  # result_data citations should help

    def test_validation_time_tracked(self):
        result = self.svc.validate(text="Hello world.", prompt="greet")
        assert result["metadata"]["validation_time_ms"] >= 0

    def test_singleton_instance(self):
        assert qa_service is not None
        assert isinstance(qa_service, QAService)
