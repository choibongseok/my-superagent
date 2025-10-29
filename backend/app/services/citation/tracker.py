"""Citation Tracker for managing citations and sources."""

import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.services.citation.models import Citation, Source, SourceType

logger = logging.getLogger(__name__)


class CitationTracker:
    """
    Manages citations and sources for research and document generation.

    Features:
        - Source registration and tracking
        - Citation generation in multiple formats (APA, MLA, Chicago)
        - Bibliography generation
        - Citation deduplication

    Usage:
        tracker = CitationTracker()

        # Add source
        source_id = tracker.add_source(
            title="LangChain Documentation",
            url="https://python.langchain.com",
            type=SourceType.WEB,
        )

        # Create citation
        citation = tracker.cite(source_id, quoted_text="LangChain is a framework...")

        # Get bibliography
        bibliography = tracker.get_bibliography(style="apa")
    """

    def __init__(self):
        """Initialize citation tracker."""
        self.sources: Dict[str, Source] = {}
        self.citations: Dict[str, Citation] = {}
        self.source_url_map: Dict[str, str] = {}  # URL -> source_id mapping

        logger.debug("CitationTracker initialized")

    def add_source(
        self,
        title: str,
        url: Optional[str] = None,
        type: SourceType = SourceType.WEB,
        author: Optional[str] = None,
        published_date: Optional[datetime] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a new source.

        Args:
            title: Source title
            url: Source URL
            type: Type of source
            author: Author name
            published_date: Publication date
            description: Source description
            metadata: Additional metadata

        Returns:
            Source ID
        """
        # Check if source already exists by URL
        if url and url in self.source_url_map:
            existing_id = self.source_url_map[url]
            logger.debug(f"Source already exists: {existing_id}")
            return existing_id

        # Generate unique ID
        source_id = str(uuid.uuid4())

        # Create source
        source = Source(
            id=source_id,
            type=type,
            title=title,
            url=url,
            author=author,
            published_date=published_date,
            description=description,
            metadata=metadata or {},
        )

        # Store source
        self.sources[source_id] = source

        # Map URL to source ID
        if url:
            self.source_url_map[url] = source_id

        logger.info(f"Added source: {source_id} - {title}")
        return source_id

    def get_source(self, source_id: str) -> Optional[Source]:
        """
        Get source by ID.

        Args:
            source_id: Source identifier

        Returns:
            Source or None
        """
        return self.sources.get(source_id)

    def cite(
        self,
        source_id: str,
        quoted_text: Optional[str] = None,
        page_number: Optional[int] = None,
        location: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Citation]:
        """
        Create a citation from a source.

        Args:
            source_id: Source identifier
            quoted_text: Quoted text
            page_number: Page number
            location: Location in document
            context: Citation context
            metadata: Additional metadata

        Returns:
            Citation or None if source not found
        """
        source = self.get_source(source_id)
        if not source:
            logger.error(f"Source not found: {source_id}")
            return None

        # Generate citation ID
        citation_id = f"cite_{len(self.citations) + 1}"

        # Create citation
        citation = Citation(
            id=citation_id,
            source=source,
            quoted_text=quoted_text,
            page_number=page_number,
            location=location,
            context=context,
            metadata=metadata or {},
        )

        # Store citation
        self.citations[citation_id] = citation

        logger.debug(f"Created citation: {citation_id} for source {source_id}")
        return citation

    def get_citation(self, citation_id: str) -> Optional[Citation]:
        """
        Get citation by ID.

        Args:
            citation_id: Citation identifier

        Returns:
            Citation or None
        """
        return self.citations.get(citation_id)

    def get_all_citations(self) -> List[Citation]:
        """
        Get all citations.

        Returns:
            List of citations
        """
        return list(self.citations.values())

    def get_all_sources(self) -> List[Source]:
        """
        Get all sources.

        Returns:
            List of sources
        """
        return list(self.sources.values())

    def get_bibliography(
        self,
        style: str = "apa",
        sort_by: str = "author",
    ) -> List[str]:
        """
        Generate bibliography from all sources.

        Args:
            style: Citation style (apa, mla, chicago)
            sort_by: Sort method (author, title, date)

        Returns:
            List of formatted citations
        """
        sources = self.get_all_sources()

        # Sort sources
        if sort_by == "author":
            sources.sort(key=lambda s: s.author or s.title)
        elif sort_by == "title":
            sources.sort(key=lambda s: s.title)
        elif sort_by == "date":
            sources.sort(
                key=lambda s: s.published_date or datetime.min,
                reverse=True,
            )

        # Format citations
        bibliography = []
        for source in sources:
            citation_text = source.to_citation_format(style=style)
            bibliography.append(citation_text)

        return bibliography

    def get_inline_citations(
        self,
        text: str,
        style: str = "apa",
    ) -> str:
        """
        Add inline citations to text.

        Args:
            text: Original text
            style: Citation style

        Returns:
            Text with inline citations
        """
        # This is a placeholder - actual implementation would need
        # more sophisticated text processing to insert citations
        logger.warning("Inline citation insertion not fully implemented")
        return text

    def clear(self) -> None:
        """Clear all sources and citations."""
        self.sources.clear()
        self.citations.clear()
        self.source_url_map.clear()
        logger.info("Cleared all citations and sources")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get citation statistics.

        Returns:
            Statistics dictionary
        """
        source_types = {}
        for source in self.sources.values():
            source_types[source.type] = source_types.get(source.type, 0) + 1

        return {
            "total_sources": len(self.sources),
            "total_citations": len(self.citations),
            "source_types": source_types,
            "unique_urls": len(self.source_url_map),
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Export tracker state to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "sources": [source.dict() for source in self.sources.values()],
            "citations": [citation.dict() for citation in self.citations.values()],
            "statistics": self.get_statistics(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CitationTracker":
        """
        Create CitationTracker from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            CitationTracker instance
        """
        tracker = cls()

        # Restore sources
        for source_data in data.get("sources", []):
            source = Source(**source_data)
            tracker.sources[source.id] = source
            if source.url:
                tracker.source_url_map[str(source.url)] = source.id

        # Restore citations
        for citation_data in data.get("citations", []):
            citation = Citation(**citation_data)
            tracker.citations[citation.id] = citation

        return tracker


__all__ = ["CitationTracker"]
