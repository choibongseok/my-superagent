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

        tracker.add_source(title="Web Article", url="https://example.com", type=SourceType.WEB)
        tracker.add_source(title="Book", type=SourceType.BOOK)
        source_id = tracker.add_source(title="Another Web", url="https://example.org", type=SourceType.WEB)

        tracker.cite(source_id, quoted_text="Test")

        stats = tracker.get_statistics()

        assert stats["total_sources"] == 3
        assert stats["total_citations"] == 1
        assert stats["source_types"][SourceType.WEB] == 2
        assert stats["source_types"][SourceType.BOOK] == 1
        assert stats["unique_urls"] == 2

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        tracker = CitationTracker()

        source_id = tracker.add_source(
            title="Test Source",
            url="https://example.com",
            author="Test Author",
        )
        tracker.cite(source_id, quoted_text="Test quote")

        # Export to dict
        data = tracker.to_dict()

        assert len(data["sources"]) == 1
        assert len(data["citations"]) == 1

        # Import from dict
        new_tracker = CitationTracker.from_dict(data)

        assert len(new_tracker.sources) == 1
        assert len(new_tracker.citations) == 1

        # Verify data integrity
        source = list(new_tracker.sources.values())[0]
        assert source.title == "Test Source"
        assert source.author == "Test Author"


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
