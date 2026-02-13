"""Tests for Citation Tracker."""

import pytest
from datetime import datetime

from app.services.citation.tracker import CitationTracker
from app.services.citation.models import Source, SourceType


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

        tracker.add_source(
            title="Web Article", url="https://example.com", type=SourceType.WEB
        )
        tracker.add_source(title="Book", type=SourceType.BOOK)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
