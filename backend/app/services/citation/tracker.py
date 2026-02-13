"""Citation Tracker for managing citations and sources."""

import logging
import math
import re
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
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

    SOURCE_AUTHORITY_WEIGHTS: Dict[SourceType, float] = {
        SourceType.DATABASE: 1.0,
        SourceType.API: 0.9,
        SourceType.ARTICLE: 0.85,
        SourceType.BOOK: 0.8,
        SourceType.DOCUMENT: 0.75,
        SourceType.WEB: 0.65,
        SourceType.VIDEO: 0.6,
        SourceType.OTHER: 0.5,
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
    def _normalize_metadata_values(cls, value: Any) -> set[str]:
        """Normalize metadata values for robust case-insensitive comparisons."""
        if isinstance(value, (list, tuple, set, frozenset)):
            candidates = value
        else:
            candidates = [value]

        normalized_values: set[str] = set()
        for candidate in candidates:
            if candidate is None:
                continue
            normalized_candidate = cls._normalize_text(str(candidate))
            if normalized_candidate:
                normalized_values.add(normalized_candidate)

        return normalized_values

    @classmethod
    def _normalize_metadata_filters(
        cls,
        metadata_filters: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, set[str]]]:
        """Normalize and validate optional metadata filter values."""
        if metadata_filters is None:
            return None
        if not isinstance(metadata_filters, Mapping):
            raise ValueError("metadata_filters must be a mapping of key/value filters")

        normalized_filters: dict[str, set[str]] = {}
        for key, value in metadata_filters.items():
            if not isinstance(key, str):
                raise ValueError("metadata_filters keys must be strings")

            normalized_key = cls._normalize_text(key)
            if not normalized_key:
                raise ValueError("metadata_filters keys cannot be blank")

            normalized_values = cls._normalize_metadata_values(value)
            if not normalized_values:
                raise ValueError(
                    f"metadata_filters for key '{key}' must include at least one non-empty value"
                )

            normalized_filters.setdefault(normalized_key, set()).update(
                normalized_values
            )

        return normalized_filters

    @staticmethod
    def _normalize_domain(value: str) -> str:
        """Normalize domain filters and source hostnames for matching."""
        if not isinstance(value, str):
            raise ValueError("domains must contain only string values")

        candidate = value.strip()
        if not candidate:
            raise ValueError("domains must contain non-empty domain values")

        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        hostname = (parsed.hostname or "").casefold().strip(".")
        if hostname.startswith("www."):
            hostname = hostname[4:]

        if not hostname:
            raise ValueError("domains must contain valid domain values")

        return hostname

    @classmethod
    def _normalize_domains(
        cls,
        domains: Optional[str | Iterable[str]],
    ) -> Optional[set[str]]:
        """Normalize optional domain filters into a comparable hostname set."""
        if domains is None:
            return None

        raw_domains: list[str]
        if isinstance(domains, str):
            raw_domains = [domains]
        else:
            raw_domains = list(domains)

        if not raw_domains:
            raise ValueError("domains must include at least one domain value")

        normalized_domains = {cls._normalize_domain(domain) for domain in raw_domains}
        if not normalized_domains:
            raise ValueError("domains must include at least one domain value")

        return normalized_domains

    @staticmethod
    def _domain_matches_allowed(hostname: str, allowed_domains: set[str]) -> bool:
        """Return True when hostname is an allowed domain or its subdomain."""
        return any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in allowed_domains
        )

    @classmethod
    def _matches_metadata_filters(
        cls,
        source_metadata: Mapping[str, Any],
        metadata_filters: Optional[Mapping[str, set[str]]],
    ) -> bool:
        """Check whether source metadata matches all normalized filters."""
        if not metadata_filters:
            return True

        normalized_metadata: dict[str, set[str]] = {}
        for key, value in source_metadata.items():
            normalized_key = cls._normalize_text(str(key))
            if not normalized_key:
                continue

            normalized_metadata.setdefault(normalized_key, set()).update(
                cls._normalize_metadata_values(value)
            )

        for key, expected_values in metadata_filters.items():
            source_values = normalized_metadata.get(key)
            if not source_values or source_values.isdisjoint(expected_values):
                return False

        return True

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
        metadata_filters: Optional[Mapping[str, Any]] = None,
        domains: Optional[str | Iterable[str]] = None,
        min_citations: Optional[int] = None,
        max_citations: Optional[int] = None,
        min_authority_score: Optional[float] = None,
        max_authority_score: Optional[float] = None,
        sort_by: Literal[
            "relevance",
            "title",
            "published_date",
            "citation_count",
            "authority",
        ] = "relevance",
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
            metadata_filters: Optional metadata constraints where each key/value
                pair must match source metadata exactly (case-insensitive). Values
                may be scalars or iterables of accepted values.
            domains: Optional domain filter(s). Accepts a single domain string
                or an iterable of domains. Matching is case-insensitive and
                includes subdomains (e.g. ``news.example.com`` matches
                ``example.com``).
            min_citations: Optional inclusive lower bound for citation count per
                source.
            max_citations: Optional inclusive upper bound for citation count per
                source.
            min_authority_score: Optional inclusive lower bound for source
                authority score, using ``SOURCE_AUTHORITY_WEIGHTS`` values in
                the ``0.0`` to ``1.0`` range.
            max_authority_score: Optional inclusive upper bound for source
                authority score, using ``SOURCE_AUTHORITY_WEIGHTS`` values in
                the ``0.0`` to ``1.0`` range.
            sort_by: Result ordering strategy. ``"relevance"`` favors textual
                score, ``"title"`` sorts alphabetically, ``"published_date"``
                sorts newest-first with undated sources last,
                ``"citation_count"`` prioritizes frequently cited sources,
                and ``"authority"`` ranks by source reliability heuristics
                based on source type (for example, databases before generic
                web pages).

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

        if min_citations is not None and min_citations < 0:
            raise ValueError("min_citations cannot be negative")

        if max_citations is not None and max_citations < 0:
            raise ValueError("max_citations cannot be negative")

        if (
            min_citations is not None
            and max_citations is not None
            and min_citations > max_citations
        ):
            raise ValueError("min_citations cannot be greater than max_citations")

        if min_authority_score is not None and not 0 <= min_authority_score <= 1:
            raise ValueError("min_authority_score must be between 0 and 1")

        if max_authority_score is not None and not 0 <= max_authority_score <= 1:
            raise ValueError("max_authority_score must be between 0 and 1")

        if (
            min_authority_score is not None
            and max_authority_score is not None
            and min_authority_score > max_authority_score
        ):
            raise ValueError(
                "min_authority_score cannot be greater than max_authority_score"
            )

        normalized_match_mode = self._normalize_text(match_mode)
        if normalized_match_mode not in {"all", "any"}:
            raise ValueError("match_mode must be 'all' or 'any'")

        normalized_sort_by = (
            self._normalize_text(str(sort_by)).replace(" ", "_").replace("-", "_")
        )
        if normalized_sort_by not in {
            "relevance",
            "title",
            "published_date",
            "citation_count",
            "authority",
        }:
            raise ValueError(
                "sort_by must be one of: relevance, title, published_date, citation_count, authority"
            )

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

        normalized_metadata_filters = self._normalize_metadata_filters(metadata_filters)
        normalized_domains = self._normalize_domains(domains)
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        ranked_matches: List[tuple[int, int, Source]] = []

        for source in self.sources.values():
            citation_count = citation_counts.get(source.id, 0)
            if min_citations is not None and citation_count < min_citations:
                continue
            if max_citations is not None and citation_count > max_citations:
                continue

            authority_score = self.SOURCE_AUTHORITY_WEIGHTS.get(source.type, 0.5)
            if (
                min_authority_score is not None
                and authority_score < min_authority_score
            ):
                continue
            if (
                max_authority_score is not None
                and authority_score > max_authority_score
            ):
                continue

            source_type_value = self._normalize_text(str(source.type))
            if (
                normalized_source_type is not None
                and source_type_value != normalized_source_type
            ):
                continue

            if normalized_domains is not None:
                source_hostname = ""
                if source.url:
                    source_hostname = self._normalize_domain(str(source.url))

                if not source_hostname or not self._domain_matches_allowed(
                    source_hostname,
                    normalized_domains,
                ):
                    continue

            if not self._matches_metadata_filters(
                source.metadata or {},
                normalized_metadata_filters,
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

                # Enhanced scoring with phrase matching and term frequency
                # Using weighted scoring with diminishing returns for repeated terms
                score = 0.0
                
                # Configurable scoring weights for maintainability
                PHRASE_WEIGHTS = {
                    "title": 20.0,
                    "description": 10.0,
                    "other": 5.0,
                }
                
                TOKEN_WEIGHTS = {
                    "title": 5.0,
                    "author": 3.0,
                    "description": 2.0,
                    "url": 1.0,
                    "metadata": 1.0,
                }
                
                # Cap frequencies to prevent keyword stuffing from dominating
                MAX_OCCURRENCES = {
                    "title": 3,
                    "author": 2,
                    "description": 3,
                }

                # Bonus for exact phrase match (significantly boosts relevance)
                if len(query_tokens) > 1 and normalized_query in searchable_text:
                    # Phrase length bonus (longer phrases are more specific)
                    phrase_specificity = min(len(query_tokens) / 5.0, 1.0)
                    
                    if normalized_query in title:
                        score += PHRASE_WEIGHTS["title"] * (1 + phrase_specificity)
                    elif normalized_query in description:
                        score += PHRASE_WEIGHTS["description"] * (1 + phrase_specificity)
                    else:
                        score += PHRASE_WEIGHTS["other"] * (1 + phrase_specificity)

                # Individual token scoring with term frequency and diminishing returns
                for token in query_tokens:
                    token_contribution = 0.0
                    
                    # Title matches are most important
                    if token in title:
                        title_count = min(title.count(token), MAX_OCCURRENCES["title"])
                        # Diminishing returns: 1st occurrence worth full, subsequent worth less
                        for i in range(title_count):
                            token_contribution += TOKEN_WEIGHTS["title"] / (1 + i * 0.5)

                    # Author matches indicate topical expertise
                    if token in author:
                        author_count = min(author.count(token), MAX_OCCURRENCES["author"])
                        for i in range(author_count):
                            token_contribution += TOKEN_WEIGHTS["author"] / (1 + i * 0.5)

                    # Description matches provide context
                    if token in description:
                        desc_count = min(description.count(token), MAX_OCCURRENCES["description"])
                        for i in range(desc_count):
                            token_contribution += TOKEN_WEIGHTS["description"] / (1 + i * 0.5)

                    # URL matches suggest relevant domain
                    if token in source_url:
                        token_contribution += TOKEN_WEIGHTS["url"]

                    # Metadata matches add supporting evidence
                    if token in metadata_text:
                        token_contribution += TOKEN_WEIGHTS["metadata"]
                    
                    score += token_contribution
                
                # Normalize score by query length to prevent long queries from dominating
                # Use logarithmic scaling to balance single-term vs multi-term queries
                # Logarithmic approach is more balanced than linear scaling
                query_length_factor = 1 + math.log(len(query_tokens)) * 0.2
                score = score / query_length_factor
            else:
                score = 0

            ranked_matches.append((score, citation_count, source))

        if normalized_sort_by == "title":
            ranked_matches.sort(
                key=lambda item: (
                    self._normalize_text(item[2].title),
                    -item[0],
                    -item[1],
                )
            )
        elif normalized_sort_by == "published_date":
            ranked_matches.sort(
                key=lambda item: (
                    item[2].published_date is None,
                    -(
                        item[2].published_date.toordinal()
                        if item[2].published_date
                        else 0
                    ),
                    self._normalize_text(item[2].title),
                )
            )
        elif normalized_sort_by == "citation_count":
            ranked_matches.sort(
                key=lambda item: (
                    -item[1],
                    -item[0],
                    self._normalize_text(item[2].title),
                )
            )
        elif normalized_sort_by == "authority":
            ranked_matches.sort(
                key=lambda item: (
                    -self.SOURCE_AUTHORITY_WEIGHTS.get(item[2].type, 0.5),
                    -item[0],
                    -item[1],
                    self._normalize_text(item[2].title),
                )
            )
        else:
            ranked_matches.sort(
                key=lambda item: (
                    -item[0],
                    -item[1],
                    self._normalize_text(item[2].title),
                )
            )

        sources = [source for _, _, source in ranked_matches]
        if limit is not None:
            sources = sources[:limit]

        return sources

    @staticmethod
    def _build_match_details(
        source: Source,
        query_tokens: list[str],
        normalized_query: str,
    ) -> Dict[str, Any]:
        """Build explainability metadata for a matched source result."""
        fields = {
            "title": CitationTracker._normalize_text(source.title),
            "author": CitationTracker._normalize_text(source.author),
            "description": CitationTracker._normalize_text(source.description),
            "url": CitationTracker._normalize_text(
                str(source.url) if source.url else ""
            ),
            "metadata": CitationTracker._normalize_text(
                " ".join(
                    f"{key} {value}" for key, value in (source.metadata or {}).items()
                )
            ),
        }

        if not query_tokens:
            return {
                "matched_fields": [],
                "matched_tokens": {},
                "query_phrase_match": False,
                "token_hit_count": 0,
            }

        matched_fields = [
            field_name
            for field_name, field_value in fields.items()
            if any(token in field_value for token in query_tokens)
        ]

        matched_tokens: Dict[str, List[str]] = {}
        token_hit_count = 0
        for token in query_tokens:
            token_fields = [
                field_name
                for field_name, field_value in fields.items()
                if token in field_value
            ]
            if token_fields:
                matched_tokens[token] = token_fields
                token_hit_count += len(token_fields)

        searchable_text = " ".join(segment for segment in fields.values() if segment)

        return {
            "matched_fields": matched_fields,
            "matched_tokens": matched_tokens,
            "query_phrase_match": bool(
                normalized_query
                and len(query_tokens) > 1
                and normalized_query in searchable_text
            ),
            "token_hit_count": token_hit_count,
        }

    def search_sources_with_details(
        self,
        query: str,
        *,
        source_type: Optional[SourceType | str] = None,
        limit: Optional[int] = None,
        match_mode: Literal["all", "any"] = "all",
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None,
        metadata_filters: Optional[Mapping[str, Any]] = None,
        domains: Optional[str | Iterable[str]] = None,
        min_citations: Optional[int] = None,
        max_citations: Optional[int] = None,
        min_authority_score: Optional[float] = None,
        max_authority_score: Optional[float] = None,
        sort_by: Literal[
            "relevance",
            "title",
            "published_date",
            "citation_count",
            "authority",
        ] = "relevance",
    ) -> List[Dict[str, Any]]:
        """Search sources and return explainable ranking metadata.

        This complements :meth:`search_sources` by exposing per-result details
        useful for UI debugging, audit logs, and ranking transparency.
        """
        matched_sources = self.search_sources(
            query,
            source_type=source_type,
            limit=limit,
            match_mode=match_mode,
            published_after=published_after,
            published_before=published_before,
            metadata_filters=metadata_filters,
            domains=domains,
            min_citations=min_citations,
            max_citations=max_citations,
            min_authority_score=min_authority_score,
            max_authority_score=max_authority_score,
            sort_by=sort_by,
        )

        normalized_query = self._normalize_text(query)
        query_tokens = [token for token in normalized_query.split(" ") if token]
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        detailed_matches: List[Dict[str, Any]] = []
        for index, source in enumerate(matched_sources, start=1):
            match_details = self._build_match_details(
                source,
                query_tokens=query_tokens,
                normalized_query=normalized_query,
            )
            detailed_matches.append(
                {
                    "rank": index,
                    "source": source,
                    "citation_count": citation_counts.get(source.id, 0),
                    "authority_score": self.SOURCE_AUTHORITY_WEIGHTS.get(
                        source.type,
                        0.5,
                    ),
                    **match_details,
                }
            )

        return detailed_matches

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

    @staticmethod
    def _confidence_level_from_score(score: float) -> str:
        """Convert numeric confidence score into a human-friendly label."""
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        return "low"

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        """Normalize datetime values into naive UTC for safe arithmetic."""
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=None)

        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _compute_recency_score(
        cls,
        published_date: Optional[datetime],
        *,
        reference_time: datetime,
        recency_window_days: int,
    ) -> float:
        """Compute recency freshness score for a single source."""
        if published_date is None:
            # Undated sources are penalized more heavily to encourage proper
            # publication metadata.
            return 0.3

        normalized_published_date = cls._normalize_datetime(published_date)
        age_days = max(
            0.0,
            (reference_time - normalized_published_date).total_seconds() / 86400,
        )

        # Use a more realistic decay curve instead of linear decay.
        if age_days <= recency_window_days * 0.1:
            # Very recent sources (within 10% of window) get near-perfect
            # scores.
            return 1.0 - (age_days / (recency_window_days * 0.1)) * 0.1
        if age_days <= recency_window_days * 0.5:
            # Moderate age (10-50% of window) - gentle decay.
            normalized_age = (age_days - recency_window_days * 0.1) / (
                recency_window_days * 0.4
            )
            return 0.9 - (normalized_age * 0.3)  # Decays from 0.9 to 0.6

        # Older sources (50-100% of window) - steeper decay.
        normalized_age = (age_days - recency_window_days * 0.5) / (
            recency_window_days * 0.5
        )
        return max(0.0, 0.6 - (normalized_age * 0.6))  # Decays from 0.6 to 0.0

    @classmethod
    def _build_source_validation_detail(
        cls,
        source: Source,
        *,
        reference_time: datetime,
        citation_count: int,
        authority_score: float,
        recency_score: float,
    ) -> Dict[str, Any]:
        """Build per-source validation breakdown metadata."""
        normalized_published_date = (
            cls._normalize_datetime(source.published_date)
            if source.published_date is not None
            else None
        )
        age_days = (
            max(
                0.0,
                (reference_time - normalized_published_date).total_seconds() / 86400,
            )
            if normalized_published_date is not None
            else None
        )

        hostname = None
        if source.url:
            parsed = urlparse(str(source.url))
            if parsed.hostname:
                hostname = parsed.hostname.casefold()

        return {
            "source_id": source.id,
            "title": source.title,
            "source_type": (
                source.type.value
                if isinstance(source.type, SourceType)
                else str(source.type)
            ),
            "domain": hostname,
            "is_cited": citation_count > 0,
            "citation_count": citation_count,
            "authority_score": round(authority_score, 3),
            "recency_score": round(recency_score, 3),
            "published_date": (
                normalized_published_date.isoformat()
                if normalized_published_date is not None
                else None
            ),
            "age_days": round(age_days, 3) if age_days is not None else None,
        }

    def get_validation_report(
        self,
        *,
        min_sources: int = 3,
        recency_window_days: int = 730,
        as_of: Optional[datetime] = None,
        include_source_breakdown: bool = False,
    ) -> Dict[str, Any]:
        """Generate a lightweight fact-check confidence report for current sources.

        The report uses deterministic heuristics so downstream consumers can show
        a trust score and explainability details without an additional LLM call.

        Args:
            min_sources: Minimum source count required for strong confidence.
            recency_window_days: Publication age window used for recency scoring.
            as_of: Optional reference timestamp for deterministic recency
                calculations. When omitted, uses current UTC time.
            include_source_breakdown: When ``True``, include per-source scoring
                details in ``source_breakdown`` for explainability/debugging.

        Returns:
            Dictionary with aggregate confidence score, level, gaps, and metrics.
        """
        if min_sources <= 0:
            raise ValueError("min_sources must be greater than 0")
        if recency_window_days <= 0:
            raise ValueError("recency_window_days must be greater than 0")

        total_sources = len(self.sources)
        if total_sources == 0:
            report: Dict[str, Any] = {
                "confidence_score": 0.0,
                "confidence_level": "low",
                "summary": "No sources available for validation yet.",
                "meets_minimum_sources": False,
                "gaps": [
                    f"Add at least {min_sources} independent sources before trusting conclusions."
                ],
                "metrics": {
                    "total_sources": 0,
                    "unique_domains": 0,
                    "cited_sources": 0,
                    "citation_coverage": 0.0,
                    "source_count_score": 0.0,
                    "domain_diversity_score": 0.0,
                    "authority_score": 0.0,
                    "recency_score": 0.0,
                },
            }
            if include_source_breakdown:
                report["source_breakdown"] = []
            return report

        reference_time = self._normalize_datetime(
            as_of if as_of is not None else datetime.now(timezone.utc)
        )
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )
        source_ids_with_citations = set(citation_counts)
        cited_sources = sum(
            1 for source_id in self.sources if source_id in source_ids_with_citations
        )
        citation_coverage = cited_sources / total_sources

        unique_domains = {
            parsed.hostname.casefold()
            for source in self.sources.values()
            if source.url
            for parsed in [urlparse(str(source.url))]
            if parsed.hostname
        }

        authority_weights = []
        recency_scores = []
        source_breakdown: List[Dict[str, Any]] = []

        for source in self.sources.values():
            authority_score_for_source = self.SOURCE_AUTHORITY_WEIGHTS.get(
                source.type,
                0.5,
            )
            authority_weights.append(authority_score_for_source)

            source_recency_score = self._compute_recency_score(
                source.published_date,
                reference_time=reference_time,
                recency_window_days=recency_window_days,
            )
            recency_scores.append(source_recency_score)

            if include_source_breakdown:
                source_breakdown.append(
                    self._build_source_validation_detail(
                        source,
                        reference_time=reference_time,
                        citation_count=citation_counts.get(source.id, 0),
                        authority_score=authority_score_for_source,
                        recency_score=source_recency_score,
                    )
                )

        source_count_score = min(total_sources / min_sources, 1.0)
        domain_diversity_score = min(len(unique_domains) / total_sources, 1.0)
        authority_score = (
            sum(authority_weights) / len(authority_weights)
            if authority_weights
            else 0.0
        )
        recency_score = (
            sum(recency_scores) / len(recency_scores) if recency_scores else 0.0
        )

        weighted_confidence = (
            (0.25 * source_count_score)
            + (0.25 * citation_coverage)
            + (0.20 * domain_diversity_score)
            + (0.15 * authority_score)
            + (0.15 * recency_score)
        )
        confidence_score = round(weighted_confidence * 100, 1)

        gaps: List[str] = []
        if total_sources < min_sources:
            gaps.append(
                f"Only {total_sources} sources collected; target is at least {min_sources}."
            )
        if citation_coverage < 0.7:
            gaps.append(
                "Citation coverage is low; cite each claim with specific supporting sources."
            )
        if total_sources > 1 and len(unique_domains) < min(2, total_sources):
            gaps.append(
                "Source diversity is low; include evidence from additional domains."
            )
        if recency_score < 0.5:
            gaps.append(
                "Most sources are outdated relative to the configured recency window."
            )

        confidence_level = self._confidence_level_from_score(confidence_score)
        summary = (
            f"Validation confidence is {confidence_level} ({confidence_score}/100) "
            f"across {total_sources} sources."
        )

        report = {
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "summary": summary,
            "meets_minimum_sources": total_sources >= min_sources,
            "gaps": gaps,
            "metrics": {
                "total_sources": total_sources,
                "unique_domains": len(unique_domains),
                "cited_sources": cited_sources,
                "citation_coverage": round(citation_coverage, 3),
                "source_count_score": round(source_count_score, 3),
                "domain_diversity_score": round(domain_diversity_score, 3),
                "authority_score": round(authority_score, 3),
                "recency_score": round(recency_score, 3),
            },
        }

        if include_source_breakdown:
            report["source_breakdown"] = sorted(
                source_breakdown,
                key=lambda item: (
                    str(item["title"]).casefold(),
                    str(item["source_id"]),
                ),
            )

        return report

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get citation statistics.

        Returns:
            Statistics dictionary
        """
        source_types = {}
        for source in self.sources.values():
            source_types[source.type] = source_types.get(source.type, 0) + 1

        # Calculate average citations per source
        total_citations = len(self.citations)
        avg_citations = total_citations / len(self.sources) if self.sources else 0.0

        # Find most and least cited sources
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )
        most_cited = citation_counts.most_common(1)
        least_cited = citation_counts.most_common()[:-2:-1] if citation_counts else []

        return {
            "total_sources": len(self.sources),
            "total_citations": total_citations,
            "average_citations_per_source": round(avg_citations, 2),
            "source_types": source_types,
            "unique_urls": len(self.source_url_map),
            "unique_source_fingerprints": len(self.source_fingerprint_map),
            "most_cited_source_id": most_cited[0][0] if most_cited else None,
            "most_cited_count": most_cited[0][1] if most_cited else 0,
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
