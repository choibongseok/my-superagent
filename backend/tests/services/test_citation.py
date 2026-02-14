"""Tests for Citation Tracker."""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.citation.tracker import CitationTracker
from app.services.citation.models import Citation, Source, SourceType


class TestCitationTracker:
    """Test suite for CitationTracker."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = CitationTracker()

        assert len(tracker.sources) == 0
        assert len(tracker.citations) == 0

    def test_add_source(self):
        """Test adding a source."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="LangChain Documentation",
            url="https://python.langchain.com",
            type=SourceType.WEB,
            author="LangChain Team",
        )

        assert source_id is not None
        assert len(tracker.sources) == 1

        source = tracker.get_source(source_id)
        assert source is not None
        assert source.title == "LangChain Documentation"
        assert source.type == SourceType.WEB

    def test_add_duplicate_source(self):
        """Test that duplicate sources return same ID."""
        tracker = CitationTracker()

        url = "https://example.com/article"

        id1 = tracker.add_source(title="Article 1", url=url)
        id2 = tracker.add_source(title="Article 1", url=url)

        assert id1 == id2
        assert len(tracker.sources) == 1

    def test_add_duplicate_source_with_normalized_url(self):
        """Test duplicate detection across equivalent URL variants."""
        tracker = CitationTracker()

        canonical = "https://example.com/article?lang=en&ref=home"
        variant = "https://EXAMPLE.com/article/?utm_source=newsletter&ref=home&lang=en#section"

        id1 = tracker.add_source(title="Canonical Article", url=canonical)
        id2 = tracker.add_source(title="Variant Article", url=variant)

        assert id1 == id2
        assert len(tracker.sources) == 1

    def test_add_duplicate_source_without_url_uses_fingerprint(self):
        """URL-less sources should dedupe by normalized type+author+title fingerprint."""
        tracker = CitationTracker()

        id1 = tracker.add_source(
            title="  Clean Architecture  ",
            type=SourceType.BOOK,
            author="Robert C. Martin",
        )
        id2 = tracker.add_source(
            title="clean architecture",
            type=SourceType.BOOK,
            author=" robert c. martin ",
        )

        assert id1 == id2
        assert len(tracker.sources) == 1

    def test_add_source_without_url_different_author_not_duplicate(self):
        """Fingerprint should keep similarly titled URL-less sources distinct by author."""
        tracker = CitationTracker()

        id1 = tracker.add_source(
            title="Deep Learning",
            type=SourceType.BOOK,
            author="Ian Goodfellow",
        )
        id2 = tracker.add_source(
            title="Deep Learning",
            type=SourceType.BOOK,
            author="Francois Chollet",
        )

        assert id1 != id2
        assert len(tracker.sources) == 2

    def test_add_source_without_url_then_with_url_reuses_and_enriches_source(self):
        """Re-adding a URL-less source with URL metadata should enrich existing entry."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Clean Architecture",
            type=SourceType.BOOK,
            author="Robert C. Martin",
        )

        reused_id = tracker.add_source(
            title=" clean architecture ",
            type=SourceType.BOOK,
            author=" robert c. martin ",
            url="https://example.com/books/clean-architecture?utm_source=newsletter",
            metadata={"isbn": "9780134494166"},
        )

        assert reused_id == source_id
        assert len(tracker.sources) == 1

        source = tracker.get_source(source_id)
        assert source is not None
        assert source.url is not None
        assert (
            str(source.url)
            == "https://example.com/books/clean-architecture?utm_source=newsletter"
        )
        assert source.metadata["isbn"] == "9780134494166"

        by_url = tracker.get_source_by_url(
            "https://example.com/books/clean-architecture"
        )
        assert by_url is not None
        assert by_url.id == source_id

    def test_get_source_by_url(self):
        """Test retrieving source by normalized URL lookup."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Normalization Test",
            url="https://example.com/path?lang=ko&ref=1",
        )

        source = tracker.get_source_by_url(
            "https://example.com/path/?utm_medium=email&ref=1&lang=ko"
        )

        assert source is not None
        assert source.id == source_id
        assert source.title == "Normalization Test"

    def test_search_sources_matches_multiple_fields_case_insensitively(self):
        """Search should match title/author/metadata and rank title matches first."""
        tracker = CitationTracker()

        title_id = tracker.add_source(
            title="Agentic Workflow Patterns",
            author="Alex Kim",
            metadata={"topic": "automation"},
        )
        author_id = tracker.add_source(
            title="Designing Reliable Systems",
            author="Agentic Researcher",
            metadata={"topic": "operations"},
        )
        metadata_id = tracker.add_source(
            title="Process Handbook",
            author="Morgan Lee",
            metadata={"notes": "best AGENTIC practices"},
        )

        matches = tracker.search_sources("agentic")

        assert [source.id for source in matches] == [title_id, author_id, metadata_id]

    def test_search_sources_supports_type_filter_and_limit(self):
        """Type filtering and result limiting should narrow search output."""
        tracker = CitationTracker()

        tracker.add_source(title="Web One", type=SourceType.WEB)
        article_id = tracker.add_source(title="Article One", type=SourceType.ARTICLE)
        tracker.add_source(title="Article Two", type=SourceType.ARTICLE)

        matches = tracker.search_sources(
            "article",
            source_type=SourceType.ARTICLE,
            limit=1,
        )

        assert len(matches) == 1
        assert matches[0].id == article_id
        assert matches[0].type == SourceType.ARTICLE

    def test_search_sources_supports_source_types_allow_list(self):
        """source_types should allow filtering by multiple source categories."""
        tracker = CitationTracker()

        article_id = tracker.add_source(
            title="Article Insight", type=SourceType.ARTICLE
        )
        tracker.add_source(title="Web Insight", type=SourceType.WEB)
        api_id = tracker.add_source(title="API Insight", type=SourceType.API)

        matches = tracker.search_sources(
            "insight",
            source_types=[SourceType.ARTICLE, "API"],
            sort_by="title",
        )

        assert [source.id for source in matches] == [api_id, article_id]

    def test_search_sources_supports_exclude_source_types_filter(self):
        """exclude_source_types should filter out matching source categories."""
        tracker = CitationTracker()

        article_id = tracker.add_source(
            title="Article Insight",
            type=SourceType.ARTICLE,
        )
        tracker.add_source(title="Web Insight", type=SourceType.WEB)
        tracker.add_source(title="API Insight", type=SourceType.API)

        matches = tracker.search_sources(
            "insight",
            exclude_source_types=["web", SourceType.API],
        )

        assert [source.id for source in matches] == [article_id]

    def test_search_sources_exclude_source_types_override_allow_list(self):
        """exclude_source_types should win when source type appears in both filters."""
        tracker = CitationTracker()

        article_id = tracker.add_source(
            title="Article Insight",
            type=SourceType.ARTICLE,
        )
        tracker.add_source(title="Web Insight", type=SourceType.WEB)

        matches = tracker.search_sources(
            "insight",
            source_types=[SourceType.ARTICLE, SourceType.WEB],
            exclude_source_types=[SourceType.WEB],
        )

        assert [source.id for source in matches] == [article_id]

    def test_search_sources_source_type_filters_validate_input(self):
        """source_type/source_types should reject conflicting or invalid payloads."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="source_type and source_types cannot be used together",
        ):
            tracker.search_sources(
                "agent",
                source_type=SourceType.WEB,
                source_types=[SourceType.ARTICLE],
            )

        with pytest.raises(
            ValueError,
            match="source_types must include at least one source type",
        ):
            tracker.search_sources("agent", source_types=[])

        with pytest.raises(
            ValueError,
            match="source_types must contain only SourceType or string values",
        ):
            tracker.search_sources("agent", source_types=[123])

        with pytest.raises(
            ValueError,
            match="exclude_source_types must include at least one source type",
        ):
            tracker.search_sources("agent", exclude_source_types=[])

        with pytest.raises(
            ValueError,
            match="exclude_source_types must contain only SourceType or string values",
        ):
            tracker.search_sources("agent", exclude_source_types=[123])

    def test_search_sources_blank_query_returns_all_sorted_by_title(self):
        """Blank search query should return all sources in stable title order."""
        tracker = CitationTracker()

        tracker.add_source(title="Zeta")
        tracker.add_source(title="alpha")
        tracker.add_source(title="Beta")

        matches = tracker.search_sources("   ")

        assert [source.title for source in matches] == ["alpha", "Beta", "Zeta"]

    def test_search_sources_rejects_non_positive_limit(self):
        """Search should validate positive limit values."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="limit must be greater than 0"):
            tracker.search_sources("agent", limit=0)

    def test_search_sources_match_mode_any_returns_partial_token_matches(self):
        """match_mode='any' should return partial token matches, unlike default all."""
        tracker = CitationTracker()

        both_id = tracker.add_source(title="Agentic Workflow Patterns")
        agentic_only_id = tracker.add_source(title="Agentic Reliability Guide")
        workflow_only_id = tracker.add_source(title="Workflow Handbook")

        matches_all = tracker.search_sources("agentic workflow")
        assert [source.id for source in matches_all] == [both_id]

        matches_any = tracker.search_sources("agentic workflow", match_mode="any")

        assert len(matches_any) == 3
        assert matches_any[0].id == both_id
        assert {source.id for source in matches_any} == {
            both_id,
            agentic_only_id,
            workflow_only_id,
        }

    def test_search_sources_rejects_invalid_match_mode(self):
        """Search should validate supported token matching modes."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="match_mode must be 'all' or 'any'"):
            tracker.search_sources("agent", match_mode="partial")

    def test_search_sources_supports_min_token_matches_filter(self):
        """min_token_matches should drop sources that match too few unique query tokens."""
        tracker = CitationTracker()

        strong_id = tracker.add_source(title="Agentic Workflow Reliability Handbook")
        medium_id = tracker.add_source(title="Agentic Workflow Playbook")
        tracker.add_source(title="Agentic Glossary")

        matches = tracker.search_sources(
            "agentic workflow reliability",
            match_mode="any",
            min_token_matches=2,
        )

        assert [source.id for source in matches] == [strong_id, medium_id]

    def test_search_sources_min_token_matches_uses_unique_query_tokens(self):
        """Repeated query tokens should not inflate min_token_matches requirements."""
        tracker = CitationTracker()

        source_id = tracker.add_source(title="Agentic Workflow Guide")

        matches = tracker.search_sources(
            "agentic agentic workflow",
            match_mode="any",
            min_token_matches=2,
        )

        assert [source.id for source in matches] == [source_id]

    def test_search_sources_rejects_invalid_min_token_matches(self):
        """min_token_matches should enforce integer, positive, and bounded values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="min_token_matches must be an integer",
        ):
            tracker.search_sources("agentic workflow", min_token_matches=1.5)

        with pytest.raises(
            ValueError,
            match="min_token_matches must be greater than 0",
        ):
            tracker.search_sources("agentic workflow", min_token_matches=0)

        with pytest.raises(
            ValueError,
            match="min_token_matches cannot exceed number of unique query tokens",
        ):
            tracker.search_sources("agentic workflow", min_token_matches=3)

    def test_search_sources_supports_max_results_per_domain_cap(self):
        """Domain diversity cap should limit duplicate hostnames in ranked output."""
        tracker = CitationTracker()

        first_example_id = tracker.add_source(
            title="Agentic Workflow Alpha",
            url="https://news.example.com/alpha",
        )
        tracker.add_source(
            title="Agentic Workflow Beta",
            url="https://blog.example.com/beta",
        )
        external_id = tracker.add_source(
            title="Agentic Workflow Gamma",
            url="https://research.org/gamma",
        )

        matches = tracker.search_sources(
            "agentic workflow",
            max_results_per_domain=1,
        )

        assert [source.id for source in matches] == [first_example_id, external_id]

    def test_search_sources_rejects_invalid_max_results_per_domain(self):
        """max_results_per_domain should validate integer and positive values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="max_results_per_domain must be an integer",
        ):
            tracker.search_sources("agent", max_results_per_domain=1.5)

        with pytest.raises(
            ValueError,
            match="max_results_per_domain must be an integer",
        ):
            tracker.search_sources("agent", max_results_per_domain=True)

        with pytest.raises(
            ValueError,
            match="max_results_per_domain must be greater than 0",
        ):
            tracker.search_sources("agent", max_results_per_domain=0)

    def test_search_sources_with_details_supports_min_token_matches_filter(self):
        """Detailed search should apply min_token_matches consistently."""
        tracker = CitationTracker()

        keep_id = tracker.add_source(title="Agentic Workflow Reliability Handbook")
        tracker.add_source(title="Workflow Notes")

        detailed = tracker.search_sources_with_details(
            "agentic workflow reliability",
            match_mode="any",
            min_token_matches=2,
        )

        assert [item["source"].id for item in detailed] == [keep_id]

    def test_search_sources_with_details_supports_max_results_per_domain_cap(self):
        """Detailed search should pass max_results_per_domain through consistently."""
        tracker = CitationTracker()

        first_example_id = tracker.add_source(
            title="Agent Reliability Alpha",
            url="https://docs.example.com/alpha",
        )
        tracker.add_source(
            title="Agent Reliability Beta",
            url="https://blog.example.com/beta",
        )
        external_id = tracker.add_source(
            title="Agent Reliability Delta",
            url="https://other.org/delta",
        )

        detailed = tracker.search_sources_with_details(
            "agent reliability",
            max_results_per_domain=1,
        )

        assert [item["source"].id for item in detailed] == [
            first_example_id,
            external_id,
        ]

    def test_search_sources_supports_include_source_ids_filter(self):
        """include_source_ids should restrict results to the provided IDs."""
        tracker = CitationTracker()

        included_first = tracker.add_source(title="Agentic Architecture")
        excluded = tracker.add_source(title="Agentic Reliability")
        included_second = tracker.add_source(title="Agentic Operations")

        matches = tracker.search_sources(
            "agentic",
            include_source_ids=[included_first, included_second],
        )

        assert [source.id for source in matches] == [
            included_first,
            included_second,
        ]
        assert excluded not in {source.id for source in matches}

    def test_search_sources_supports_exclude_source_ids_filter(self):
        """exclude_source_ids should remove matching IDs from otherwise valid results."""
        tracker = CitationTracker()

        kept_id = tracker.add_source(title="Prompt Engineering Handbook")
        excluded_id = tracker.add_source(title="Prompt Injection Notes")

        matches = tracker.search_sources(
            "prompt",
            exclude_source_ids=[excluded_id],
        )

        assert [source.id for source in matches] == [kept_id]

    def test_search_sources_source_id_filters_validate_input(self):
        """Source ID filters should reject empty and non-string values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="include_source_ids must include at least one source id",
        ):
            tracker.search_sources("agent", include_source_ids=[])

        with pytest.raises(
            ValueError,
            match="exclude_source_ids must contain only string source ids",
        ):
            tracker.search_sources("agent", exclude_source_ids=[123])

        with pytest.raises(
            ValueError,
            match="exclude_source_ids must contain non-empty source ids",
        ):
            tracker.search_sources("agent", exclude_source_ids=["   "])

    def test_search_sources_supports_sort_by_citation_count(self):
        """sort_by='citation_count' should prioritize most-cited sources first."""
        tracker = CitationTracker()

        heavily_cited_id = tracker.add_source(title="Agent Ops Handbook")
        lightly_cited_id = tracker.add_source(title="Agent Ops Primer")
        uncited_id = tracker.add_source(title="Agent Ops Glossary")

        tracker.cite(heavily_cited_id, quoted_text="One")
        tracker.cite(heavily_cited_id, quoted_text="Two")
        tracker.cite(lightly_cited_id, quoted_text="One")

        matches = tracker.search_sources("agent ops", sort_by="citation_count")

        assert [source.id for source in matches] == [
            heavily_cited_id,
            lightly_cited_id,
            uncited_id,
        ]

    def test_search_sources_supports_sort_by_authority(self):
        """sort_by='authority' should prioritize trusted source types first."""
        tracker = CitationTracker()

        database_id = tracker.add_source(
            title="National Statistics Database",
            type=SourceType.DATABASE,
        )
        article_id = tracker.add_source(
            title="Peer-reviewed Analysis",
            type=SourceType.ARTICLE,
        )
        web_id = tracker.add_source(
            title="General Blog Post",
            type=SourceType.WEB,
        )

        matches = tracker.search_sources("", sort_by="authority")

        assert [source.id for source in matches] == [database_id, article_id, web_id]

    def test_search_sources_supports_sort_by_published_date(self):
        """sort_by='published_date' should rank newest sources first and undated last."""
        tracker = CitationTracker()

        older_id = tracker.add_source(
            title="AI Brief 2021",
            published_date=datetime(2021, 5, 1),
            type=SourceType.ARTICLE,
        )
        newest_id = tracker.add_source(
            title="AI Brief 2025",
            published_date=datetime(2025, 1, 10),
            type=SourceType.ARTICLE,
        )
        undated_id = tracker.add_source(
            title="AI Brief (Undated)",
            type=SourceType.ARTICLE,
        )

        matches = tracker.search_sources("ai brief", sort_by="published_date")

        assert [source.id for source in matches] == [newest_id, older_id, undated_id]

    def test_search_sources_supports_sort_by_recency(self):
        """sort_by='recency' should prioritize fresher sources and penalize undated ones."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        fresh_id = tracker.add_source(
            title="Fresh AI Brief",
            published_date=anchor_time - timedelta(days=7),
            type=SourceType.ARTICLE,
        )
        mid_id = tracker.add_source(
            title="Mid-term AI Brief",
            published_date=anchor_time - timedelta(days=180),
            type=SourceType.ARTICLE,
        )
        undated_id = tracker.add_source(
            title="Undated AI Brief",
            type=SourceType.ARTICLE,
        )

        matches = tracker.search_sources(
            "ai brief",
            sort_by="recency",
            as_of=anchor_time,
            recency_window_days=365,
        )

        assert [source.id for source in matches] == [fresh_id, mid_id, undated_id]

    def test_search_sources_supports_sort_by_hybrid(self):
        """sort_by='hybrid' should blend lexical and source-quality signals."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        lexical_first_id = tracker.add_source(
            title="Agent Reliability Workflow Workflow Handbook",
            type=SourceType.WEB,
            published_date=anchor_time - timedelta(days=500),
        )
        quality_first_id = tracker.add_source(
            title="Agent Reliability Workflow Reference",
            type=SourceType.DATABASE,
            published_date=anchor_time - timedelta(days=3),
        )

        tracker.cite(quality_first_id, quoted_text="Primary source")
        tracker.cite(quality_first_id, quoted_text="Secondary source")

        relevance_matches = tracker.search_sources(
            "agent reliability workflow",
            sort_by="relevance",
            as_of=anchor_time,
            recency_window_days=365,
        )
        hybrid_matches = tracker.search_sources(
            "agent reliability workflow",
            sort_by="hybrid",
            as_of=anchor_time,
            recency_window_days=365,
        )

        assert relevance_matches[0].id == lexical_first_id
        assert hybrid_matches[0].id == quality_first_id

    def test_search_sources_rejects_invalid_recency_sort_arguments(self):
        """Recency sorting options should validate window and profile values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError, match="recency_window_days must be greater than 0"
        ):
            tracker.search_sources("ai", sort_by="recency", recency_window_days=0)

        with pytest.raises(
            ValueError,
            match="recency_profile must be one of: strict, balanced, lenient",
        ):
            tracker.search_sources(
                "ai", sort_by="recency", recency_profile="aggressive"
            )

    def test_search_sources_supports_min_and_max_recency_score_filters(self):
        """Recency score bounds should filter stale and fresh sources deterministically."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        fresh_id = tracker.add_source(
            title="Fresh AI Brief",
            published_date=anchor_time - timedelta(days=7),
            type=SourceType.ARTICLE,
        )
        stale_id = tracker.add_source(
            title="Stale AI Brief",
            published_date=anchor_time - timedelta(days=300),
            type=SourceType.ARTICLE,
        )
        undated_id = tracker.add_source(
            title="Undated AI Brief",
            type=SourceType.ARTICLE,
        )

        fresh_only = tracker.search_sources(
            "ai brief",
            as_of=anchor_time,
            recency_window_days=365,
            min_recency_score=0.5,
        )
        assert [source.id for source in fresh_only] == [fresh_id]

        stale_or_undated = tracker.search_sources(
            "ai brief",
            as_of=anchor_time,
            recency_window_days=365,
            max_recency_score=0.35,
        )
        assert {source.id for source in stale_or_undated} == {stale_id, undated_id}
        assert fresh_id not in {source.id for source in stale_or_undated}

    def test_search_sources_rejects_invalid_recency_score_filters(self):
        """Recency score filters should enforce valid 0..1 ranges and bounds."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="min_recency_score must be between 0 and 1",
        ):
            tracker.search_sources("ai", min_recency_score=-0.1)

        with pytest.raises(
            ValueError,
            match="max_recency_score must be between 0 and 1",
        ):
            tracker.search_sources("ai", max_recency_score=1.1)

        with pytest.raises(
            ValueError,
            match="min_recency_score cannot be greater than max_recency_score",
        ):
            tracker.search_sources(
                "ai",
                min_recency_score=0.8,
                max_recency_score=0.4,
            )

    def test_search_sources_supports_sort_by_title(self):
        """sort_by='title' should sort alphabetically regardless of relevance score."""
        tracker = CitationTracker()

        tracker.add_source(title="Zeta Guide")
        tracker.add_source(title="alpha guide")
        tracker.add_source(title="Beta Guide")

        matches = tracker.search_sources("guide", sort_by="title")

        assert [source.title for source in matches] == [
            "alpha guide",
            "Beta Guide",
            "Zeta Guide",
        ]

    def test_search_sources_rejects_invalid_sort_by(self):
        """Search should validate supported sort_by values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="sort_by must be one of: relevance, hybrid, title, published_date, citation_count, authority, recency",
        ):
            tracker.search_sources("agent", sort_by="custom")

    def test_search_sources_with_details_returns_ranked_explainability_metadata(self):
        """Detailed search results should include rank, counts, and match signals."""
        tracker = CitationTracker()

        primary_id = tracker.add_source(
            title="Agentic Workflow Handbook",
            author="Alex Kim",
            metadata={"topic": "automation"},
            type=SourceType.ARTICLE,
        )
        secondary_id = tracker.add_source(
            title="Workflow Notes",
            author="Morgan Lee",
            metadata={"topic": "agentic operations"},
            type=SourceType.WEB,
        )

        tracker.cite(primary_id, quoted_text="Primary reference")
        tracker.cite(primary_id, quoted_text="Second reference")

        detailed = tracker.search_sources_with_details(
            "agentic workflow",
            sort_by="relevance",
        )

        assert [item["source"].id for item in detailed] == [primary_id, secondary_id]

        first = detailed[0]
        assert first["rank"] == 1
        assert first["citation_count"] == 2
        assert first["authority_score"] == pytest.approx(0.85)
        assert first["relevance_score"] > 0
        assert first["query_phrase_match"] is True
        assert "title" in first["matched_fields"]
        assert "agentic" in first["matched_tokens"]
        assert first["token_hit_count"] >= 2

    def test_search_sources_with_details_includes_recency_score_and_profile_effect(
        self,
    ):
        """Detailed search should expose recency_score and honor recency profile tuning."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        tracker.add_source(
            title="Architecture Brief",
            published_date=anchor_time - timedelta(days=180),
            type=SourceType.DOCUMENT,
        )

        strict_results = tracker.search_sources_with_details(
            "architecture",
            sort_by="recency",
            as_of=anchor_time,
            recency_window_days=365,
            recency_profile="strict",
        )
        lenient_results = tracker.search_sources_with_details(
            "architecture",
            sort_by="recency",
            as_of=anchor_time,
            recency_window_days=365,
            recency_profile="lenient",
        )

        strict_score = strict_results[0]["recency_score"]
        lenient_score = lenient_results[0]["recency_score"]

        assert isinstance(strict_score, float)
        assert isinstance(lenient_score, float)
        assert strict_score < lenient_score

    def test_search_sources_with_details_includes_hybrid_score(self):
        """Detailed search should expose the computed hybrid ranking score."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        source_id = tracker.add_source(
            title="Agent Reliability Workflow Reference",
            type=SourceType.DATABASE,
            published_date=anchor_time - timedelta(days=2),
        )
        tracker.cite(source_id, quoted_text="Operational requirement")

        detailed = tracker.search_sources_with_details(
            "agent reliability workflow",
            sort_by="hybrid",
            as_of=anchor_time,
            recency_window_days=365,
        )

        first = detailed[0]
        assert first["source"].id == source_id
        assert "hybrid_score" in first
        assert first["hybrid_score"] == tracker._compute_hybrid_score(
            relevance_score=first["relevance_score"],
            citation_count=first["citation_count"],
            authority_score=first["authority_score"],
            recency_score=first["recency_score"],
        )

    def test_search_sources_with_details_handles_blank_queries(self):
        """Blank queries should still return stable details without token metadata."""
        tracker = CitationTracker()

        tracker.add_source(title="Zeta Brief")
        tracker.add_source(title="Alpha Brief")

        detailed = tracker.search_sources_with_details("   ", sort_by="title")

        assert [item["source"].title for item in detailed] == [
            "Alpha Brief",
            "Zeta Brief",
        ]
        assert all(item["matched_fields"] == [] for item in detailed)
        assert all(item["matched_tokens"] == {} for item in detailed)
        assert all(item["query_phrase_match"] is False for item in detailed)
        assert all(item["token_hit_count"] == 0 for item in detailed)
        assert all(item["relevance_score"] == 0.0 for item in detailed)

    def test_search_sources_with_details_supports_source_id_filters(self):
        """Detailed search should pass include/exclude source filters through."""
        tracker = CitationTracker()

        include_id = tracker.add_source(title="Async Python Handbook")
        excluded_id = tracker.add_source(title="Async Runtime Notes")

        detailed = tracker.search_sources_with_details(
            "async",
            include_source_ids=[include_id, excluded_id],
            exclude_source_ids=[excluded_id],
        )

        assert [item["source"].id for item in detailed] == [include_id]

    def test_search_sources_with_details_supports_source_types_allow_list(self):
        """Detailed search should pass source_types filters through."""
        tracker = CitationTracker()

        include_id = tracker.add_source(title="Agent API Guide", type=SourceType.API)
        tracker.add_source(title="Agent Web Guide", type=SourceType.WEB)

        detailed = tracker.search_sources_with_details(
            "agent guide",
            source_types=["api"],
        )

        assert [item["source"].id for item in detailed] == [include_id]

    def test_search_sources_with_details_supports_exclude_source_types(self):
        """Detailed search should apply exclude_source_types consistently."""
        tracker = CitationTracker()

        include_id = tracker.add_source(
            title="Agent API Guide",
            type=SourceType.API,
        )
        tracker.add_source(title="Agent Web Guide", type=SourceType.WEB)

        detailed = tracker.search_sources_with_details(
            "agent guide",
            exclude_source_types=["web"],
        )

        assert [item["source"].id for item in detailed] == [include_id]

    def test_search_sources_supports_publication_date_range_filters(self):
        """Date range filters should include only sources published in-range."""
        tracker = CitationTracker()

        old_id = tracker.add_source(
            title="Legacy AI Report",
            published_date=datetime(2021, 5, 20),
            type=SourceType.ARTICLE,
        )
        in_range_id = tracker.add_source(
            title="Modern AI Report",
            published_date=datetime(2024, 6, 1),
            type=SourceType.ARTICLE,
        )
        tracker.add_source(
            title="Undated AI Report",
            type=SourceType.ARTICLE,
        )

        matches = tracker.search_sources(
            "ai report",
            source_type=SourceType.ARTICLE,
            published_after=datetime(2023, 1, 1),
            published_before=datetime(2024, 12, 31),
        )

        assert [source.id for source in matches] == [in_range_id]
        assert old_id not in {source.id for source in matches}

    def test_search_sources_rejects_invalid_publication_date_range(self):
        """published_after should not allow values later than published_before."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="published_after cannot be later than published_before",
        ):
            tracker.search_sources(
                "ai",
                published_after=datetime(2025, 1, 1),
                published_before=datetime(2024, 12, 31),
            )

    def test_search_sources_supports_min_and_max_citations_filters(self):
        """Citation count bounds should filter sources by how often they are cited."""
        tracker = CitationTracker()

        heavily_cited_id = tracker.add_source(title="Heavily Cited")
        lightly_cited_id = tracker.add_source(title="Lightly Cited")
        uncited_id = tracker.add_source(title="Uncited")

        tracker.cite(heavily_cited_id, quoted_text="One")
        tracker.cite(heavily_cited_id, quoted_text="Two")
        tracker.cite(lightly_cited_id, quoted_text="One")

        at_least_one = tracker.search_sources("cited", min_citations=1)
        assert [source.id for source in at_least_one] == [
            heavily_cited_id,
            lightly_cited_id,
        ]

        at_most_one = tracker.search_sources("cited", max_citations=1)
        assert [source.id for source in at_most_one] == [
            lightly_cited_id,
            uncited_id,
        ]

        bounded = tracker.search_sources("cited", min_citations=1, max_citations=1)
        assert [source.id for source in bounded] == [lightly_cited_id]

    def test_search_sources_rejects_invalid_citation_bound_filters(self):
        """Citation bounds should reject negative values and invalid ranges."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="min_citations cannot be negative"):
            tracker.search_sources("ai", min_citations=-1)

        with pytest.raises(ValueError, match="max_citations cannot be negative"):
            tracker.search_sources("ai", max_citations=-1)

        with pytest.raises(
            ValueError,
            match="min_citations cannot be greater than max_citations",
        ):
            tracker.search_sources("ai", min_citations=2, max_citations=1)

    def test_search_sources_supports_min_and_max_authority_score_filters(self):
        """Authority score bounds should filter by trusted source type weights."""
        tracker = CitationTracker()

        database_id = tracker.add_source(
            title="AI Standards Registry",
            type=SourceType.DATABASE,
        )
        article_id = tracker.add_source(
            title="AI Strategy Review",
            type=SourceType.ARTICLE,
        )
        web_id = tracker.add_source(
            title="AI Community Blog",
            type=SourceType.WEB,
        )

        high_trust_matches = tracker.search_sources(
            "ai",
            min_authority_score=0.8,
            sort_by="authority",
        )
        assert [source.id for source in high_trust_matches] == [database_id, article_id]

        low_trust_matches = tracker.search_sources(
            "ai",
            max_authority_score=0.7,
            sort_by="authority",
        )
        assert [source.id for source in low_trust_matches] == [web_id]

    def test_search_sources_rejects_invalid_authority_score_filters(self):
        """Authority score filters should enforce valid 0..1 ranges and bounds."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="min_authority_score must be between 0 and 1",
        ):
            tracker.search_sources("ai", min_authority_score=-0.1)

        with pytest.raises(
            ValueError,
            match="max_authority_score must be between 0 and 1",
        ):
            tracker.search_sources("ai", max_authority_score=1.1)

        with pytest.raises(
            ValueError,
            match="min_authority_score cannot be greater than max_authority_score",
        ):
            tracker.search_sources(
                "ai", min_authority_score=0.9, max_authority_score=0.6
            )

    def test_search_sources_supports_min_relevance_score_filter(self):
        """min_relevance_score should remove weaker lexical matches."""
        tracker = CitationTracker()

        strong_id = tracker.add_source(title="Agentic Workflow Handbook")
        tracker.add_source(
            title="Operational Notes",
            metadata={"topic": "agentic"},
        )

        matches = tracker.search_sources(
            "agentic workflow",
            match_mode="any",
            min_relevance_score=8.0,
        )

        assert [source.id for source in matches] == [strong_id]

    def test_search_sources_rejects_negative_min_relevance_score(self):
        """min_relevance_score cannot be negative."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="min_relevance_score cannot be negative"):
            tracker.search_sources("agent", min_relevance_score=-0.1)

    def test_search_sources_supports_max_relevance_score_filter(self):
        """max_relevance_score should remove strongest matches above threshold."""
        tracker = CitationTracker()

        weak_id = tracker.add_source(
            title="Operational Notes",
            metadata={"topic": "agentic"},
        )
        tracker.add_source(title="Agentic Workflow Handbook")

        matches = tracker.search_sources(
            "agentic workflow",
            match_mode="any",
            max_relevance_score=5.0,
        )

        assert [source.id for source in matches] == [weak_id]

    def test_search_sources_rejects_invalid_max_relevance_score_filters(self):
        """Relevance score bounds should enforce non-negative and valid ranges."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="max_relevance_score cannot be negative"):
            tracker.search_sources("agent", max_relevance_score=-0.1)

        with pytest.raises(
            ValueError,
            match="min_relevance_score cannot be greater than max_relevance_score",
        ):
            tracker.search_sources(
                "agent",
                min_relevance_score=10.0,
                max_relevance_score=5.0,
            )

    def test_search_sources_with_details_supports_relevance_score_range_filters(self):
        """Detailed search should pass through min/max relevance constraints."""
        tracker = CitationTracker()

        strong_id = tracker.add_source(title="Agent Reliability Handbook")
        weak_id = tracker.add_source(
            title="Reliability digest",
            metadata={"tag": "agent"},
        )

        detailed = tracker.search_sources_with_details(
            "agent reliability",
            match_mode="any",
            min_relevance_score=0.5,
            max_relevance_score=8.0,
        )

        assert [item["source"].id for item in detailed] == [weak_id]
        assert strong_id not in {item["source"].id for item in detailed}
        assert 0.5 <= detailed[0]["relevance_score"] <= 8.0

    def test_search_sources_with_details_supports_recency_score_range_filters(self):
        """Detailed search should pass through min/max recency score constraints."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        fresh_id = tracker.add_source(
            title="Fresh Reliability Notes",
            published_date=anchor_time - timedelta(days=5),
            type=SourceType.ARTICLE,
        )
        tracker.add_source(
            title="Legacy Reliability Notes",
            published_date=anchor_time - timedelta(days=320),
            type=SourceType.ARTICLE,
        )

        detailed = tracker.search_sources_with_details(
            "reliability notes",
            as_of=anchor_time,
            recency_window_days=365,
            min_recency_score=0.5,
        )

        assert [item["source"].id for item in detailed] == [fresh_id]
        assert detailed[0]["recency_score"] >= 0.5

    def test_search_sources_supports_case_insensitive_metadata_filters(self):
        """Metadata filters should match keys/values regardless of casing."""
        tracker = CitationTracker()

        ai_ops_id = tracker.add_source(
            title="AI Ops Playbook",
            metadata={"topic": "AI", "region": "KR"},
        )
        tracker.add_source(
            title="AI Safety Brief",
            metadata={"topic": "safety", "region": "US"},
        )

        matches = tracker.search_sources(
            "ai",
            metadata_filters={"TOPIC": "ai", "region": "kr"},
        )

        assert [source.id for source in matches] == [ai_ops_id]

    def test_search_sources_metadata_filters_support_multiple_allowed_values(self):
        """Metadata filter values can be provided as an allow-list iterable."""
        tracker = CitationTracker()

        kr_id = tracker.add_source(
            title="Regional AI Overview",
            metadata={"region": "KR", "topic": "ai"},
        )
        jp_id = tracker.add_source(
            title="Regional Data Overview",
            metadata={"region": "JP", "topic": "data"},
        )
        tracker.add_source(
            title="US AI Overview",
            metadata={"region": "US", "topic": "ai"},
        )

        matches = tracker.search_sources(
            "overview",
            metadata_filters={"region": ["kr", "jp"]},
        )

        assert [source.id for source in matches] == [kr_id, jp_id]

    def test_search_sources_supports_domain_filters_with_subdomain_matching(self):
        """Domain filters should match configured domains and their subdomains."""
        tracker = CitationTracker()

        example_id = tracker.add_source(
            title="AI Operations Update",
            url="https://news.example.com/ai-ops",
        )
        research_id = tracker.add_source(
            title="AI Research Digest",
            url="https://www.research.org/posts/weekly",
        )
        tracker.add_source(
            title="AI Community Notes",
            url="https://community.other.net/ai",
        )
        tracker.add_source(
            title="AI Internal Memo",
        )

        matches = tracker.search_sources(
            "ai",
            domains=["example.com", "https://RESEARCH.org"],
        )

        assert {source.id for source in matches} == {example_id, research_id}

    def test_search_sources_supports_exclude_domain_filters(self):
        """exclude_domains should remove matching hosts while preserving other matches."""
        tracker = CitationTracker()

        keep_id = tracker.add_source(
            title="AI Operations Update",
            url="https://news.example.com/ai-ops",
        )
        tracker.add_source(
            title="AI Research Digest",
            url="https://www.research.org/posts/weekly",
        )
        no_url_id = tracker.add_source(title="AI Internal Memo")

        matches = tracker.search_sources(
            "ai",
            exclude_domains=["https://RESEARCH.org"],
        )

        assert {source.id for source in matches} == {keep_id, no_url_id}

    def test_search_sources_exclude_domains_override_allow_list(self):
        """When both filters are set, matching exclude_domains should win."""
        tracker = CitationTracker()

        keep_id = tracker.add_source(
            title="AI Operations Update",
            url="https://news.example.com/ai-ops",
        )
        tracker.add_source(
            title="AI Research Digest",
            url="https://www.research.org/posts/weekly",
        )

        matches = tracker.search_sources(
            "ai",
            domains=["example.com", "research.org"],
            exclude_domains=["research.org"],
        )

        assert [source.id for source in matches] == [keep_id]

    def test_search_sources_with_details_respects_exclude_domain_filters(self):
        """Detailed search should apply exclude_domains consistently."""
        tracker = CitationTracker()

        keep_id = tracker.add_source(
            title="Agent Reliability Notes",
            url="https://docs.example.com/reliability",
        )
        tracker.add_source(
            title="Agent Reliability Community",
            url="https://community.bad.net/reliability",
        )

        detailed_matches = tracker.search_sources_with_details(
            "agent reliability",
            exclude_domains=["bad.net"],
        )

        assert [item["source"].id for item in detailed_matches] == [keep_id]


    def test_search_sources_supports_has_url_filter(self):
        """has_url should allow filtering URL-backed and URL-less sources."""
        tracker = CitationTracker()

        with_url_id = tracker.add_source(
            title="AI Reliability Update",
            url="https://example.com/reliability",
        )
        without_url_id = tracker.add_source(
            title="AI Reliability Internal Memo",
        )

        with_url_matches = tracker.search_sources("ai reliability", has_url=True)
        without_url_matches = tracker.search_sources("ai reliability", has_url=False)

        assert [source.id for source in with_url_matches] == [with_url_id]
        assert [source.id for source in without_url_matches] == [without_url_id]

    def test_search_sources_with_details_supports_has_url_filter(self):
        """Detailed search should pass has_url filtering to the base search."""
        tracker = CitationTracker()

        tracker.add_source(
            title="Agent Deployment Runbook",
            url="https://docs.example.com/agent-deploy",
        )
        without_url_id = tracker.add_source(
            title="Agent Deployment Internal Checklist",
        )

        detailed = tracker.search_sources_with_details(
            "agent deployment",
            has_url=False,
        )

        assert [item["source"].id for item in detailed] == [without_url_id]

    def test_search_sources_rejects_invalid_has_url_filter(self):
        """has_url should accept only boolean values when provided."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="has_url must be a boolean when provided",
        ):
            tracker.search_sources("ai", has_url="true")  # type: ignore[arg-type]

    def test_search_sources_rejects_invalid_domains_filters(self):
        """Domain filters should validate payload shape and non-empty values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="domains must include at least one domain value",
        ):
            tracker.search_sources("ai", domains=[])

        with pytest.raises(
            ValueError,
            match="domains must contain non-empty domain values",
        ):
            tracker.search_sources("ai", domains=["   "])

        with pytest.raises(
            ValueError,
            match="domains must contain only string values",
        ):
            tracker.search_sources("ai", domains=[123])  # type: ignore[list-item]

        with pytest.raises(
            ValueError,
            match="domains must include at least one domain value",
        ):
            tracker.search_sources("ai", exclude_domains=[])

        with pytest.raises(
            ValueError,
            match="domains must contain non-empty domain values",
        ):
            tracker.search_sources("ai", exclude_domains=["   "])

        with pytest.raises(
            ValueError,
            match="domains must contain only string values",
        ):
            tracker.search_sources(
                "ai",
                exclude_domains=[123],  # type: ignore[list-item]
            )

    def test_search_sources_rejects_invalid_metadata_filters(self):
        """Search should validate metadata filter payload shape and values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="metadata_filters must be a mapping of key/value filters",
        ):
            tracker.search_sources("ai", metadata_filters=[("topic", "ai")])

        with pytest.raises(ValueError, match="metadata_filters keys cannot be blank"):
            tracker.search_sources("ai", metadata_filters={"   ": "ai"})

        with pytest.raises(
            ValueError,
            match="must include at least one non-empty value",
        ):
            tracker.search_sources("ai", metadata_filters={"topic": []})

    def test_create_citation(self):
        """Test creating a citation."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Test Article",
            url="https://example.com",
            author="John Doe",
        )

        citation = tracker.cite(
            source_id=source_id,
            quoted_text="This is a test quote.",
            page_number=42,
        )

        assert citation is not None
        assert citation.source.title == "Test Article"
        assert citation.quoted_text == "This is a test quote."
        assert citation.page_number == 42

    def test_create_citation_invalid_source(self):
        """Test creating citation with invalid source."""
        tracker = CitationTracker()

        citation = tracker.cite(
            source_id="nonexistent",
            quoted_text="Test",
        )

        assert citation is None

    def test_get_all_citations(self):
        """Test getting all citations."""
        tracker = CitationTracker()

        source1_id = tracker.add_source(title="Source 1", url="https://example.com/1")
        source2_id = tracker.add_source(title="Source 2", url="https://example.com/2")

        tracker.cite(source1_id, quoted_text="Quote 1")
        tracker.cite(source2_id, quoted_text="Quote 2")
        tracker.cite(source1_id, quoted_text="Quote 3")

        citations = tracker.get_all_citations()
        assert len(citations) == 3

    def test_get_bibliography_apa(self):
        """Test bibliography generation in APA style."""
        tracker = CitationTracker()

        tracker.add_source(
            title="Understanding AI",
            url="https://example.com/ai",
            author="Jane Smith",
            published_date=datetime(2024, 1, 1),
            type=SourceType.ARTICLE,
        )

        bibliography = tracker.get_bibliography(style="apa")

        assert len(bibliography) == 1
        assert "Jane Smith" in bibliography[0]
        assert "2024" in bibliography[0]
        assert "Understanding AI" in bibliography[0]

    def test_get_bibliography_mla(self):
        """Test bibliography generation in MLA style."""
        tracker = CitationTracker()

        tracker.add_source(
            title="Machine Learning Basics",
            url="https://example.com/ml",
            author="Bob Johnson",
            type=SourceType.WEB,
        )

        bibliography = tracker.get_bibliography(style="mla")

        assert len(bibliography) == 1
        assert "Bob Johnson" in bibliography[0]
        assert "Machine Learning Basics" in bibliography[0]

    def test_get_bibliography_harvard(self):
        """Test bibliography generation in Harvard style."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Machine Learning Basics",
            url="https://example.com/ml",
            author="Bob Johnson",
            published_date=datetime(2023, 4, 15),
            type=SourceType.WEB,
        )
        source = tracker.get_source(source_id)
        assert source is not None
        source.accessed_date = datetime(2026, 2, 14)

        bibliography = tracker.get_bibliography(style="harvard")

        assert len(bibliography) == 1
        assert "Bob Johnson (2023)." in bibliography[0]
        assert "Machine Learning Basics." in bibliography[0]
        assert "Available at: https://example.com/ml." in bibliography[0]
        assert "Accessed 14 February 2026." in bibliography[0]

    def test_get_bibliography_sorted(self):
        """Test bibliography sorting."""
        tracker = CitationTracker()

        tracker.add_source(title="Zebra Article", author="Zebra Author")
        tracker.add_source(title="Alpha Article", author="Alpha Author")
        tracker.add_source(title="Beta Article", author="Beta Author")

        bibliography = tracker.get_bibliography(sort_by="author")

        # Check alphabetical order by author
        assert "Alpha Author" in bibliography[0]
        assert "Beta Author" in bibliography[1]
        assert "Zebra Author" in bibliography[2]

    def test_get_inline_citations_replaces_citation_placeholders(self):
        """Test replacing [[cite:<id>]] placeholders with inline citation text."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="AI Safety 101",
            author="Jane Doe",
            published_date=datetime(2024, 1, 1),
        )
        citation = tracker.cite(source_id, quoted_text="Alignment is hard.")
        assert citation is not None

        rendered = tracker.get_inline_citations(
            f"AI safety is important [[cite:{citation.id}]].",
            style="apa",
        )

        assert rendered == "AI safety is important (Jane Doe, 2024)."

    def test_get_inline_citations_supports_source_placeholders(self):
        """Test replacing [[source:<id>]] placeholders without creating citations."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Agent Design",
            author="Ada Lovelace",
            type=SourceType.ARTICLE,
        )

        rendered = tracker.get_inline_citations(
            f"Reference design guidance [[source:{source_id}]].",
            style="mla",
        )

        assert rendered == "Reference design guidance (Ada Lovelace)."
        assert len(tracker.citations) == 0

    def test_get_inline_citations_supports_harvard_style(self):
        """Inline placeholder rendering should support Harvard style output."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="AI Reliability Guide",
            author="Jane Doe",
            published_date=datetime(2025, 6, 1),
            type=SourceType.DOCUMENT,
        )
        citation = tracker.cite(source_id, quoted_text="Verify every claim")
        assert citation is not None

        rendered = tracker.get_inline_citations(
            f"Evidence is documented [[cite:{citation.id}]].",
            style="harvard",
        )

        assert rendered == "Evidence is documented (Jane Doe, 2025)."

    def test_get_inline_citations_keeps_unknown_placeholders(self):
        """Unknown placeholders should remain unchanged for safer debugging."""
        tracker = CitationTracker()

        original = "No data yet [[cite:missing_id]]."
        rendered = tracker.get_inline_citations(original)

        assert rendered == original

    def test_delete_citation_returns_true_only_for_existing_ids(self):
        """Deleting citations should be idempotent and report whether removal happened."""
        tracker = CitationTracker()
        source_id = tracker.add_source(title="Test", url="https://example.com")
        citation = tracker.cite(source_id, quoted_text="Test")
        assert citation is not None

        assert tracker.delete_citation(citation.id) is True
        assert tracker.get_citation(citation.id) is None
        assert tracker.delete_citation(citation.id) is False

    def test_delete_citations_returns_per_id_status_and_deduplicates_inputs(self):
        """Bulk citation deletion should report outcomes once per unique id."""
        tracker = CitationTracker()
        source_id = tracker.add_source(title="Batch Citation Source")
        citation_one = tracker.cite(source_id, quoted_text="One")
        citation_two = tracker.cite(source_id, quoted_text="Two")

        assert citation_one is not None
        assert citation_two is not None

        result = tracker.delete_citations(
            [citation_one.id, citation_one.id, "missing-citation", citation_two.id]
        )

        assert result == {
            citation_one.id: True,
            "missing-citation": False,
            citation_two.id: True,
        }
        assert tracker.get_citation(citation_one.id) is None
        assert tracker.get_citation(citation_two.id) is None

    def test_delete_citations_validates_batch_input(self):
        """Bulk citation deletion should reject empty and malformed id payloads."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="citation_ids must include at least one id",
        ):
            tracker.delete_citations([])

        with pytest.raises(
            ValueError,
            match="citation_ids must contain only string ids",
        ):
            tracker.delete_citations([123])

        with pytest.raises(
            ValueError,
            match="citation_ids must contain non-empty ids",
        ):
            tracker.delete_citations(["   "])

    def test_delete_source_cascade_removes_source_citations_and_lookups(self):
        """Cascade deletion should remove source, citation references, and lookup indexes."""
        tracker = CitationTracker()
        source_id = tracker.add_source(
            title="Clean Architecture",
            type=SourceType.BOOK,
            author="Robert C. Martin",
            url="https://example.com/books/clean-architecture?utm_source=newsletter",
        )
        citation = tracker.cite(source_id, quoted_text="Boundaries matter")
        assert citation is not None

        assert tracker.delete_source(source_id, cascade=True) is True

        assert tracker.get_source(source_id) is None
        assert tracker.get_citation(citation.id) is None
        assert (
            tracker.get_source_by_url("https://example.com/books/clean-architecture")
            is None
        )
        duplicate_id = tracker.add_source(
            title="clean architecture",
            type=SourceType.BOOK,
            author="robert c. martin",
        )
        assert duplicate_id != source_id

    def test_delete_source_without_cascade_rejects_when_citations_exist(self):
        """Non-cascade source deletion should fail if dependent citations remain."""
        tracker = CitationTracker()
        source_id = tracker.add_source(title="Test", url="https://example.com")
        citation = tracker.cite(source_id, quoted_text="Test")
        assert citation is not None

        assert tracker.delete_source(source_id, cascade=False) is False
        assert tracker.get_source(source_id) is not None
        assert tracker.get_citation(citation.id) is not None

    def test_delete_sources_supports_bulk_deletion_with_mixed_outcomes(self):
        """Bulk source deletion should return per-id statuses in stable order."""
        tracker = CitationTracker()
        removable_id = tracker.add_source(title="Removable")
        blocked_id = tracker.add_source(title="Blocked")
        tracker.cite(blocked_id, quoted_text="Still referenced")

        result = tracker.delete_sources(
            [removable_id, blocked_id, "missing-source", removable_id],
            cascade=False,
        )

        assert result == {
            removable_id: True,
            blocked_id: False,
            "missing-source": False,
        }
        assert tracker.get_source(removable_id) is None
        assert tracker.get_source(blocked_id) is not None

    def test_delete_sources_validates_batch_input(self):
        """Bulk source deletion should reject empty and malformed id payloads."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="source_ids must include at least one id",
        ):
            tracker.delete_sources([])

        with pytest.raises(
            ValueError,
            match="source_ids must contain only string ids",
        ):
            tracker.delete_sources([123])

        with pytest.raises(
            ValueError,
            match="source_ids must contain non-empty ids",
        ):
            tracker.delete_sources(["   "])

    def test_clear_tracker(self):
        """Test clearing all citations and sources."""
        tracker = CitationTracker()

        tracker.add_source(title="Test", url="https://example.com")
        source_id = tracker.add_source(title="Test 2", url="https://example.com/2")
        tracker.cite(source_id, quoted_text="Test")

        assert len(tracker.sources) == 2
        assert len(tracker.citations) == 1

        tracker.clear()

        assert len(tracker.sources) == 0
        assert len(tracker.citations) == 0

    def test_get_statistics(self):
        """Test getting citation statistics."""
        tracker = CitationTracker()

        web_source_id = tracker.add_source(
            title="Web Article", url="https://example.com", type=SourceType.WEB
        )
        book_source_id = tracker.add_source(title="Book", type=SourceType.BOOK)
        source_id = tracker.add_source(
            title="Another Web", url="https://example.org", type=SourceType.WEB
        )

        tracker.cite(source_id, quoted_text="Test")

        stats = tracker.get_statistics()

        assert stats["total_sources"] == 3
        assert stats["total_citations"] == 1
        assert stats["source_types"][SourceType.WEB] == 2
        assert stats["source_types"][SourceType.BOOK] == 1
        assert stats["unique_urls"] == 2
        assert stats["unique_source_fingerprints"] == 3
        assert stats["most_cited_source_id"] == source_id
        assert stats["most_cited_count"] == 1
        assert stats["least_cited_count"] == 0
        assert stats["least_cited_source_id"] in {web_source_id, book_source_id}
        assert stats["cited_source_count"] == 1
        assert stats["uncited_source_count"] == 2
        assert stats["citation_coverage"] == pytest.approx(0.333, abs=0.001)
        assert stats["citation_counts_by_source"][source_id] == 1
        assert stats["citation_counts_by_source"][web_source_id] == 0

    def test_get_statistics_includes_uncited_sources_in_most_and_least_cited(self):
        """Most/least cited stats should remain deterministic even when all counts are zero."""
        tracker = CitationTracker()

        alpha_id = tracker.add_source(title="Alpha")
        beta_id = tracker.add_source(title="Beta")

        stats = tracker.get_statistics()

        assert stats["total_citations"] == 0
        assert stats["most_cited_count"] == 0
        assert stats["least_cited_count"] == 0
        assert stats["most_cited_source_id"] == alpha_id
        assert stats["least_cited_source_id"] == alpha_id
        assert stats["citation_counts_by_source"] == {alpha_id: 0, beta_id: 0}

    def test_get_validation_report_returns_low_confidence_when_no_sources(self):
        """Validation report should clearly explain empty evidence state."""
        tracker = CitationTracker()

        report = tracker.get_validation_report(min_sources=2)

        assert report["confidence_score"] == 0.0
        assert report["confidence_level"] == "low"
        assert report["meets_minimum_sources"] is False
        assert report["metrics"]["total_sources"] == 0
        assert report["gaps"]

    def test_get_validation_report_scores_diverse_recent_cited_sources_high(self):
        """Diverse and well-cited fresh sources should produce high confidence."""
        tracker = CitationTracker()

        api_source_id = tracker.add_source(
            title="Official API Reference",
            url="https://docs.example.com/api/reference",
            type=SourceType.API,
            published_date=datetime.utcnow(),
            author="Example API Team",
        )
        article_source_id = tracker.add_source(
            title="Peer Reviewed AI Study",
            url="https://journal.example.org/ai-study",
            type=SourceType.ARTICLE,
            published_date=datetime.utcnow(),
            author="Kim et al.",
        )
        db_source_id = tracker.add_source(
            title="Regulatory Database Update",
            url="https://data.example.net/updates/2026",
            type=SourceType.DATABASE,
            published_date=datetime.utcnow(),
            author="Gov Data Portal",
        )

        for source_id in (api_source_id, article_source_id, db_source_id):
            tracker.cite(source_id, quoted_text="Validated statement")

        report = tracker.get_validation_report(min_sources=3)

        assert report["confidence_level"] == "high"
        assert report["confidence_score"] >= 80
        assert report["meets_minimum_sources"] is True
        assert report["metrics"]["unique_domains"] == 3
        assert report["gaps"] == []

    def test_get_validation_report_highlights_low_coverage_and_stale_sources(self):
        """Report should explain confidence gaps when evidence quality is weak."""
        tracker = CitationTracker()

        cited_source_id = tracker.add_source(
            title="Old Blog Post",
            url="https://blog.example.com/legacy-ai",
            type=SourceType.WEB,
            published_date=datetime(2018, 1, 1),
        )
        tracker.add_source(
            title="Another Old Blog",
            url="https://blog.example.com/old-entry",
            type=SourceType.WEB,
            published_date=datetime(2017, 1, 1),
        )

        tracker.cite(cited_source_id, quoted_text="Single supporting quote")

        report = tracker.get_validation_report(min_sources=3, recency_window_days=365)

        assert report["confidence_level"] == "low"
        assert report["metrics"]["citation_coverage"] == pytest.approx(0.5)
        assert any("target is at least 3" in gap for gap in report["gaps"])
        assert any("Citation coverage is low" in gap for gap in report["gaps"])
        assert any("Source diversity is low" in gap for gap in report["gaps"])
        assert any("outdated" in gap for gap in report["gaps"])

    def test_get_validation_report_rejects_invalid_arguments(self):
        """Validation report inputs must enforce positive bounds."""
        tracker = CitationTracker()

        with pytest.raises(ValueError, match="min_sources must be greater than 0"):
            tracker.get_validation_report(min_sources=0)

        with pytest.raises(
            ValueError,
            match="recency_window_days must be greater than 0",
        ):
            tracker.get_validation_report(recency_window_days=0)

    def test_get_validation_report_supports_as_of_for_deterministic_recency(self):
        """The optional as_of timestamp should make recency scoring deterministic."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        source_id = tracker.add_source(
            title="Fresh API Changelog",
            url="https://docs.example.com/changelog",
            type=SourceType.API,
            published_date=anchor_time - timedelta(days=3),
        )
        tracker.cite(source_id, quoted_text="Latest breaking changes")

        first = tracker.get_validation_report(
            as_of=anchor_time,
            recency_window_days=90,
        )
        second = tracker.get_validation_report(
            as_of=anchor_time,
            recency_window_days=90,
        )

        assert first["confidence_score"] == second["confidence_score"]
        assert first["metrics"]["recency_score"] == second["metrics"]["recency_score"]

    def test_get_validation_report_supports_recency_profile_tuning(self):
        """Recency profile should tune how strongly age impacts freshness scoring."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        source_id = tracker.add_source(
            title="Baseline Architecture Guide",
            url="https://docs.example.com/architecture/baseline",
            type=SourceType.DOCUMENT,
            published_date=anchor_time - timedelta(days=180),
        )
        tracker.cite(source_id, quoted_text="Long-lived architectural principle")

        strict_report = tracker.get_validation_report(
            as_of=anchor_time,
            recency_window_days=365,
            recency_profile="strict",
        )
        balanced_report = tracker.get_validation_report(
            as_of=anchor_time,
            recency_window_days=365,
            recency_profile="balanced",
        )
        lenient_report = tracker.get_validation_report(
            as_of=anchor_time,
            recency_window_days=365,
            recency_profile="lenient",
        )

        assert strict_report["metrics"]["recency_profile"] == "strict"
        assert balanced_report["metrics"]["recency_profile"] == "balanced"
        assert lenient_report["metrics"]["recency_profile"] == "lenient"

        assert (
            strict_report["metrics"]["recency_score"]
            < balanced_report["metrics"]["recency_score"]
            < lenient_report["metrics"]["recency_score"]
        )

    def test_get_validation_report_rejects_invalid_recency_profile(self):
        """Validation report should reject unsupported recency profile values."""
        tracker = CitationTracker()

        with pytest.raises(
            ValueError,
            match="recency_profile must be one of: strict, balanced, lenient",
        ):
            tracker.get_validation_report(recency_profile="aggressive")

    def test_get_validation_report_includes_source_breakdown_when_requested(self):
        """Detailed report mode should expose per-source confidence metadata."""
        tracker = CitationTracker()
        anchor_time = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

        cited_source_id = tracker.add_source(
            title="AI Reliability Checklist",
            url="https://docs.example.com/reliability",
            type=SourceType.DOCUMENT,
            published_date=anchor_time - timedelta(days=5),
        )
        uncited_source_id = tracker.add_source(
            title="Legacy Blog Summary",
            url="https://blog.example.org/legacy",
            type=SourceType.WEB,
            published_date=anchor_time - timedelta(days=500),
        )
        tracker.cite(cited_source_id, quoted_text="Use checklists for launches")

        report = tracker.get_validation_report(
            as_of=anchor_time,
            include_source_breakdown=True,
        )

        assert "source_breakdown" in report
        assert len(report["source_breakdown"]) == 2

        by_source_id = {item["source_id"]: item for item in report["source_breakdown"]}
        cited_entry = by_source_id[cited_source_id]
        uncited_entry = by_source_id[uncited_source_id]

        assert cited_entry["is_cited"] is True
        assert cited_entry["citation_count"] == 1
        assert cited_entry["domain"] == "docs.example.com"
        assert cited_entry["source_type"] == SourceType.DOCUMENT.value
        assert cited_entry["age_days"] == pytest.approx(5.0, abs=0.001)

        assert uncited_entry["is_cited"] is False
        assert uncited_entry["citation_count"] == 0
        assert uncited_entry["domain"] == "blog.example.org"
        assert uncited_entry["source_type"] == SourceType.WEB.value
        assert uncited_entry["age_days"] == pytest.approx(500.0, abs=0.001)

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Test Source",
            url="https://example.com",
            author="Test Author",
        )
        tracker.add_source(
            title="Clean Code",
            type=SourceType.BOOK,
            author="Robert C. Martin",
        )
        tracker.cite(source_id, quoted_text="Test quote")

        # Export to dict
        data = tracker.to_dict()

        assert len(data["sources"]) == 2
        assert len(data["citations"]) == 1

        # Import from dict
        new_tracker = CitationTracker.from_dict(data)

        assert len(new_tracker.sources) == 2
        assert len(new_tracker.citations) == 1

        # Verify URL source data integrity
        source = new_tracker.get_source(source_id)
        assert source is not None
        assert source.title == "Test Source"
        assert source.author == "Test Author"

        # URL map should be restored with normalization
        found = new_tracker.get_source_by_url("https://example.com/?utm_source=test")
        assert found is not None
        assert found.id == source.id

        # Fingerprint map should also be restored for URL-less sources
        duplicate_book_id = new_tracker.add_source(
            title=" clean code ",
            type=SourceType.BOOK,
            author="robert c. martin",
        )
        assert len(new_tracker.sources) == 2

        clean_code_source = [
            existing
            for existing in new_tracker.sources.values()
            if existing.title == "Clean Code"
        ][0]
        assert duplicate_book_id == clean_code_source.id


class TestSource:
    """Test suite for Source model."""

    def test_source_creation(self):
        """Test creating a source."""
        source = Source(
            id="test_id",
            type=SourceType.WEB,
            title="Test Title",
            url="https://example.com",
            author="Test Author",
        )

        assert source.id == "test_id"
        assert source.title == "Test Title"
        assert source.type == SourceType.WEB

    def test_citation_format_apa(self):
        """Test APA citation format."""
        source = Source(
            id="test_id",
            type=SourceType.ARTICLE,
            title="AI Research",
            url="https://example.com/ai",
            author="Jane Doe",
            published_date=datetime(2024, 1, 1),
        )

        citation = source.to_citation_format(style="apa")

        assert "Jane Doe" in citation
        assert "2024" in citation
        assert "AI Research" in citation

    def test_citation_format_mla(self):
        """Test MLA citation format."""
        source = Source(
            id="test_id",
            type=SourceType.WEB,
            title="Machine Learning Guide",
            url="https://example.com/ml",
            author="John Smith",
        )

        citation = source.to_citation_format(style="mla")

        assert "John Smith" in citation
        assert '"Machine Learning Guide"' in citation

    def test_citation_format_harvard(self):
        """Test Harvard citation format."""
        source = Source(
            id="test_id",
            type=SourceType.ARTICLE,
            title="AI Reliability in Production",
            url="https://example.com/ai-reliability",
            author="Jane Doe",
            published_date=datetime(2024, 1, 1),
            accessed_date=datetime(2026, 2, 14),
        )

        citation = source.to_citation_format(style="harvard")

        assert "Jane Doe (2024)." in citation
        assert "AI Reliability in Production." in citation
        assert "Available at: https://example.com/ai-reliability." in citation
        assert "Accessed 14 February 2026." in citation

    def test_citation_format_harvard_handles_missing_author_and_date(self):
        """Harvard format should fall back to title + n.d. when metadata is missing."""
        source = Source(
            id="test_id",
            type=SourceType.WEB,
            title="Untitled Reference",
            url="https://example.com/reference",
            accessed_date=datetime(2026, 2, 14),
        )

        citation = source.to_citation_format(style="harvard")

        assert citation.startswith("Untitled Reference (n.d.).")
        assert citation.count("Untitled Reference") == 1

    def test_inline_citation_harvard(self):
        """Inline citation rendering should support Harvard style."""
        source = Source(
            id="source_id",
            type=SourceType.ARTICLE,
            title="Reliable Systems",
            author="Alex Kim",
            published_date=datetime(2023, 5, 1),
        )
        citation = Citation(id="citation_id", source=source)

        inline = citation.to_inline_citation(style="harvard")

        assert inline == "(Alex Kim, 2023)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
