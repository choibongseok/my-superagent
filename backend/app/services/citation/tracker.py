"""Citation Tracker for managing citations and sources."""

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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

    TRACKING_QUERY_PARAMS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
    }

    def __init__(self):
        """Initialize citation tracker."""
        self.sources: Dict[str, Source] = {}
        self.citations: Dict[str, Citation] = {}
        self.source_url_map: Dict[str, str] = {}  # normalized URL -> source_id mapping
        # source_type|author|title fingerprint -> source_id mapping
        self.source_fingerprint_map: Dict[str, str] = {}

        logger.debug("CitationTracker initialized")

    @classmethod
    def _normalize_url(cls, url: str) -> str:
        """Normalize URLs so semantically identical links deduplicate cleanly."""
        parsed = urlparse(url.strip())

        scheme = (parsed.scheme or "https").lower()

        hostname = (parsed.hostname or "").lower()
        port = parsed.port
        if port and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            netloc = f"{hostname}:{port}"
        else:
            netloc = hostname

        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")

        filtered_query_params = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in cls.TRACKING_QUERY_PARAMS
        ]
        filtered_query_params.sort()
        query = urlencode(filtered_query_params, doseq=True)

        return urlunparse((scheme, netloc, path, "", query, ""))

    @classmethod
    def _canonicalize_url(cls, url: Optional[str]) -> Optional[str]:
        """Return normalized URL if present and parseable."""
        if not url:
            return None

        try:
            return cls._normalize_url(url)
        except Exception:
            logger.warning("Failed to normalize URL: %s", url)
            return url

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        """Normalize free-form text for stable deduplication fingerprints."""
        if not value:
            return ""

        return " ".join(value.split()).casefold()

    @classmethod
    def _build_source_fingerprint(
        cls,
        title: str,
        source_type: SourceType | str,
        author: Optional[str],
    ) -> str:
        """Build deterministic fingerprint for URL-less sources."""
        normalized_title = cls._normalize_text(title)
        normalized_author = cls._normalize_text(author)

        source_type_value = (
            source_type.value
            if isinstance(source_type, SourceType)
            else str(source_type)
        )
        normalized_type = cls._normalize_text(source_type_value)

        return f"{normalized_type}|{normalized_author}|{normalized_title}"

    def _enrich_existing_source(
        self,
        source: Source,
        *,
        url: Optional[str],
        canonical_url: Optional[str],
        author: Optional[str],
        published_date: Optional[datetime],
        description: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Backfill missing source fields when duplicates are re-added."""
        if canonical_url:
            self.source_url_map[canonical_url] = source.id
            if not source.url and url:
                source.url = url

        if not source.author and author:
            source.author = author

        if source.published_date is None and published_date is not None:
            source.published_date = published_date

        if not source.description and description:
            source.description = description

        if metadata:
            for key, value in metadata.items():
                source.metadata.setdefault(key, value)

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
        canonical_url = self._canonicalize_url(url)
        source_fingerprint = self._build_source_fingerprint(title, type, author)

        # Check if source already exists by canonical URL
        if canonical_url and canonical_url in self.source_url_map:
            existing_id = self.source_url_map[canonical_url]
            logger.debug(f"Source already exists by URL: {existing_id}")
            return existing_id

        # Dedupe by metadata fingerprint even when URL is present so URL-less
        # entries can be enriched later without creating duplicates.
        if source_fingerprint in self.source_fingerprint_map:
            existing_id = self.source_fingerprint_map[source_fingerprint]
            existing_source = self.sources.get(existing_id)
            if existing_source:
                self._enrich_existing_source(
                    existing_source,
                    url=url,
                    canonical_url=canonical_url,
                    author=author,
                    published_date=published_date,
                    description=description,
                    metadata=metadata,
                )

            logger.debug(f"Source already exists by fingerprint: {existing_id}")
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

        # Map canonical URL to source ID
        if canonical_url:
            self.source_url_map[canonical_url] = source_id

        self.source_fingerprint_map[source_fingerprint] = source_id

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

    def get_source_by_url(self, url: str) -> Optional[Source]:
        """
        Get source by URL using canonical URL normalization.

        Args:
            url: Source URL

        Returns:
            Source or None
        """
        canonical_url = self._canonicalize_url(url)
        if not canonical_url:
            return None

        source_id = self.source_url_map.get(canonical_url)
        if not source_id:
            return None

        return self.get_source(source_id)

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

    def search_sources(
        self,
        query: str,
        *,
        source_type: Optional[SourceType | str] = None,
        limit: Optional[int] = None,
        match_mode: Literal["all", "any"] = "all",
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None,
    ) -> List[Source]:
        """Search sources with lightweight relevance ranking.

        Search is case-insensitive and matches across title, author,
        description, URL, and metadata fields.

        Args:
            query: Search text. Blank query returns all sources.
            source_type: Optional source type filter.
            limit: Optional max number of results. Must be > 0 when set.
            match_mode: Token matching strategy. ``"all"`` requires every
                query token to appear in the searchable source text, while
                ``"any"`` returns sources that match at least one token.
            published_after: Optional lower-bound date filter (inclusive).
            published_before: Optional upper-bound date filter (inclusive).

        Returns:
            Ranked list of matching sources.
        """
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if (
            published_after is not None
            and published_before is not None
            and published_after > published_before
        ):
            raise ValueError("published_after cannot be later than published_before")

        normalized_match_mode = self._normalize_text(match_mode)
        if normalized_match_mode not in {"all", "any"}:
            raise ValueError("match_mode must be 'all' or 'any'")

        normalized_query = self._normalize_text(query)
        query_tokens = [token for token in normalized_query.split(" ") if token]

        normalized_source_type: Optional[str] = None
        if source_type is not None:
            normalized_source_type = (
                source_type.value
                if isinstance(source_type, SourceType)
                else str(source_type)
            )
            normalized_source_type = self._normalize_text(normalized_source_type)

        ranked_matches: List[tuple[int, Source]] = []

        for source in self.sources.values():
            source_type_value = self._normalize_text(str(source.type))
            if (
                normalized_source_type is not None
                and source_type_value != normalized_source_type
            ):
                continue

            if published_after is not None or published_before is not None:
                published_date = source.published_date
                if published_date is None:
                    continue
                if published_after is not None and published_date < published_after:
                    continue
                if published_before is not None and published_date > published_before:
                    continue

            title = self._normalize_text(source.title)
            author = self._normalize_text(source.author)
            description = self._normalize_text(source.description)
            source_url = self._normalize_text(str(source.url) if source.url else "")
            metadata_text = self._normalize_text(
                " ".join(
                    f"{key} {value}" for key, value in (source.metadata or {}).items()
                )
            )

            searchable_text = " ".join(
                segment
                for segment in (title, author, description, source_url, metadata_text)
                if segment
            )

            if query_tokens:
                if normalized_match_mode == "all":
                    has_match = all(token in searchable_text for token in query_tokens)
                else:
                    has_match = any(token in searchable_text for token in query_tokens)

                if not has_match:
                    continue

                score = 0
                for token in query_tokens:
                    if token in title:
                        score += 5
                    if token in author:
                        score += 3
                    if token in description:
                        score += 2
                    if token in source_url:
                        score += 1
                    if token in metadata_text:
                        score += 1
            else:
                score = 0

            ranked_matches.append((score, source))

        ranked_matches.sort(
            key=lambda item: (-item[0], self._normalize_text(item[1].title))
        )

        sources = [source for _, source in ranked_matches]
        if limit is not None:
            sources = sources[:limit]

        return sources

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
        Replace citation placeholders with inline citation text.

        Supported placeholders:
            - [[cite:<citation_id>]]
            - [[source:<source_id>]]

        Args:
            text: Original text
            style: Citation style

        Returns:
            Text with inline citations rendered where placeholders exist
        """

        pattern = re.compile(
            r"\[\[\s*(?P<kind>cite|citation|source)\s*:\s*(?P<id>[^\]\s]+)\s*\]\]",
            flags=re.IGNORECASE,
        )

        def _render_placeholder(match: re.Match[str]) -> str:
            ref_kind = match.group("kind").lower()
            ref_id = match.group("id")

            citation: Optional[Citation] = None
            if ref_kind in {"cite", "citation"}:
                citation = self.get_citation(ref_id)
            elif ref_kind == "source":
                source = self.get_source(ref_id)
                if source:
                    citation = Citation(id=f"source_{ref_id}", source=source)

            if not citation:
                logger.warning("Citation placeholder not found: %s", match.group(0))
                return match.group(0)

            return citation.to_inline_citation(style=style)

        return pattern.sub(_render_placeholder, text)

    def delete_citation(self, citation_id: str) -> bool:
        """Delete a citation by ID.

        Args:
            citation_id: Citation identifier.

        Returns:
            ``True`` if a citation was removed, ``False`` when not found.
        """
        if citation_id not in self.citations:
            return False

        self.citations.pop(citation_id, None)
        logger.debug("Deleted citation: %s", citation_id)
        return True

    def delete_source(self, source_id: str, cascade: bool = True) -> bool:
        """Delete a source by ID.

        Args:
            source_id: Source identifier.
            cascade: When ``True`` (default), remove citations that reference
                this source. When ``False``, deletion is rejected if dependent
                citations exist.

        Returns:
            ``True`` if the source was deleted, ``False`` when not found or when
            ``cascade`` is ``False`` and dependent citations exist.
        """
        source = self.sources.get(source_id)
        if source is None:
            return False

        dependent_citation_ids = [
            citation.id
            for citation in self.citations.values()
            if citation.source.id == source_id
        ]

        if dependent_citation_ids and not cascade:
            logger.warning(
                "Cannot delete source %s: %d dependent citations exist",
                source_id,
                len(dependent_citation_ids),
            )
            return False

        # Remove source lookups first to keep maps consistent even if source
        # metadata was enriched after creation.
        self.source_url_map = {
            canonical_url: mapped_source_id
            for canonical_url, mapped_source_id in self.source_url_map.items()
            if mapped_source_id != source_id
        }
        self.source_fingerprint_map = {
            fingerprint: mapped_source_id
            for fingerprint, mapped_source_id in self.source_fingerprint_map.items()
            if mapped_source_id != source_id
        }

        self.sources.pop(source_id, None)
        for citation_id in dependent_citation_ids:
            self.delete_citation(citation_id)

        logger.info(
            "Deleted source %s (removed %d dependent citations)",
            source_id,
            len(dependent_citation_ids),
        )
        return True

    def clear(self) -> None:
        """Clear all sources and citations."""
        self.sources.clear()
        self.citations.clear()
        self.source_url_map.clear()
        self.source_fingerprint_map.clear()
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
            "unique_source_fingerprints": len(self.source_fingerprint_map),
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
                canonical_url = tracker._canonicalize_url(str(source.url))
                if canonical_url:
                    tracker.source_url_map[canonical_url] = source.id

            source_fingerprint = tracker._build_source_fingerprint(
                title=source.title,
                source_type=source.type,
                author=source.author,
            )
            tracker.source_fingerprint_map[source_fingerprint] = source.id

        # Restore citations
        for citation_data in data.get("citations", []):
            citation = Citation(**citation_data)
            tracker.citations[citation.id] = citation

        return tracker


__all__ = ["CitationTracker"]
