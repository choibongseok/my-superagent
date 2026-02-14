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

    PHRASE_WEIGHTS: Dict[str, float] = {
        "title": 20.0,
        "description": 10.0,
        "other": 5.0,
    }

    TOKEN_WEIGHTS: Dict[str, float] = {
        "title": 5.0,
        "author": 3.0,
        "description": 2.0,
        "url": 1.0,
        "metadata": 1.0,
    }

    MAX_OCCURRENCES: Dict[str, int] = {
        "title": 3,
        "author": 2,
        "description": 3,
    }

    # Multipliers applied to source age before scoring recency.
    # - strict: penalize older sources more aggressively.
    # - balanced: current default behavior.
    # - lenient: tolerate older sources for evergreen domains.
    RECENCY_PROFILE_FACTORS: Dict[str, float] = {
        "strict": 1.35,
        "balanced": 1.0,
        "lenient": 0.75,
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

    @classmethod
    def _normalize_source_ids(
        cls,
        source_ids: Optional[str | Iterable[str]],
        *,
        argument_name: str,
    ) -> Optional[set[str]]:
        """Normalize optional source-id filters into a stable set."""
        if source_ids is None:
            return None

        raw_source_ids: list[Any]
        if isinstance(source_ids, str):
            raw_source_ids = [source_ids]
        else:
            raw_source_ids = list(source_ids)

        if not raw_source_ids:
            raise ValueError(f"{argument_name} must include at least one source id")

        normalized_source_ids: set[str] = set()
        for source_id in raw_source_ids:
            if not isinstance(source_id, str):
                raise ValueError(f"{argument_name} must contain only string source ids")

            normalized_source_id = source_id.strip()
            if not normalized_source_id:
                raise ValueError(f"{argument_name} must contain non-empty source ids")

            normalized_source_ids.add(normalized_source_id)

        return normalized_source_ids

    @classmethod
    def _normalize_source_types(
        cls,
        source_types: Optional[SourceType | str | Iterable[SourceType | str]],
        *,
        argument_name: str,
    ) -> Optional[set[str]]:
        """Normalize optional source-type filters into a stable set."""
        if source_types is None:
            return None

        raw_source_types: list[Any]
        if isinstance(source_types, (SourceType, str)):
            raw_source_types = [source_types]
        else:
            raw_source_types = list(source_types)

        if not raw_source_types:
            raise ValueError(f"{argument_name} must include at least one source type")

        normalized_source_types: set[str] = set()
        for source_type in raw_source_types:
            if isinstance(source_type, SourceType):
                source_type_value = source_type.value
            elif isinstance(source_type, str):
                source_type_value = source_type
            else:
                raise ValueError(
                    f"{argument_name} must contain only SourceType or string values"
                )

            normalized_source_type = cls._normalize_text(source_type_value)
            if not normalized_source_type:
                raise ValueError(
                    f"{argument_name} must contain non-empty source type values"
                )

            normalized_source_types.add(normalized_source_type)

        return normalized_source_types

    @staticmethod
    def _domain_matches_allowed(hostname: str, allowed_domains: set[str]) -> bool:
        """Return True when hostname is an allowed domain or its subdomain."""
        return any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in allowed_domains
        )

    @classmethod
    def _extract_source_hostname(cls, source: Source) -> str | None:
        """Extract a normalized domain bucket used for diversity capping."""
        if not source.url:
            return None

        try:
            hostname = cls._normalize_domain(str(source.url))
        except ValueError:
            return None

        parts = hostname.split(".")
        if len(parts) <= 2:
            return hostname

        # Heuristic eTLD+1 collapse keeps related subdomains together
        # (for example, ``news.example.com`` and ``blog.example.com``).
        return ".".join(parts[-2:])

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

    def _compute_relevance_score(
        self,
        source: Source,
        *,
        query_tokens: list[str],
        normalized_query: str,
    ) -> float:
        """Compute deterministic relevance score for a source/query pair."""
        if not query_tokens:
            return 0.0

        title = self._normalize_text(source.title)
        author = self._normalize_text(source.author)
        description = self._normalize_text(source.description)
        source_url = self._normalize_text(str(source.url) if source.url else "")
        metadata_text = self._normalize_text(
            " ".join(f"{key} {value}" for key, value in (source.metadata or {}).items())
        )

        searchable_text = " ".join(
            segment
            for segment in (title, author, description, source_url, metadata_text)
            if segment
        )

        score = 0.0

        if len(query_tokens) > 1 and normalized_query in searchable_text:
            phrase_specificity = min(len(query_tokens) / 5.0, 1.0)

            if normalized_query in title:
                score += self.PHRASE_WEIGHTS["title"] * (1 + phrase_specificity)
            elif normalized_query in description:
                score += self.PHRASE_WEIGHTS["description"] * (1 + phrase_specificity)
            else:
                score += self.PHRASE_WEIGHTS["other"] * (1 + phrase_specificity)

        for token in query_tokens:
            token_contribution = 0.0

            if token in title:
                title_count = min(title.count(token), self.MAX_OCCURRENCES["title"])
                for i in range(title_count):
                    token_contribution += self.TOKEN_WEIGHTS["title"] / (1 + i * 0.5)

            if token in author:
                author_count = min(author.count(token), self.MAX_OCCURRENCES["author"])
                for i in range(author_count):
                    token_contribution += self.TOKEN_WEIGHTS["author"] / (1 + i * 0.5)

            if token in description:
                desc_count = min(
                    description.count(token),
                    self.MAX_OCCURRENCES["description"],
                )
                for i in range(desc_count):
                    token_contribution += self.TOKEN_WEIGHTS["description"] / (
                        1 + i * 0.5
                    )

            if token in source_url:
                token_contribution += self.TOKEN_WEIGHTS["url"]

            if token in metadata_text:
                token_contribution += self.TOKEN_WEIGHTS["metadata"]

            score += token_contribution

        # Smooth logarithmic penalty that increases gradually with query length
        # without discontinuities. The 0.15 multiplier balances behavior while
        # ensuring continuous scoring across all query lengths.
        query_length_factor = 1 + math.log(len(query_tokens) + 1) * 0.15

        score = score / query_length_factor
        return round(score, 2)

    @staticmethod
    def _compute_hybrid_score(
        *,
        relevance_score: float,
        citation_count: int,
        authority_score: float,
        recency_score: float,
    ) -> float:
        """Blend lexical and quality signals into a single ranking score.

        The weighting intentionally favors source quality signals
        (authority/recency/citation traction) while still preserving lexical
        relevance as the primary anchor.
        """
        citation_signal = math.log1p(max(citation_count, 0))
        hybrid_score = (
            relevance_score
            + (authority_score * 8.0)
            + (recency_score * 5.0)
            + (citation_signal * 2.5)
        )
        return round(hybrid_score, 2)

    def search_sources(
        self,
        query: str,
        *,
        source_type: Optional[SourceType | str] = None,
        source_types: Optional[SourceType | str | Iterable[SourceType | str]] = None,
        exclude_source_types: Optional[
            SourceType | str | Iterable[SourceType | str]
        ] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        match_mode: Literal["all", "any", "phrase"] = "all",
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None,
        min_age_days: Optional[int] = None,
        max_age_days: Optional[int] = None,
        metadata_filters: Optional[Mapping[str, Any]] = None,
        domains: Optional[str | Iterable[str]] = None,
        exclude_domains: Optional[str | Iterable[str]] = None,
        has_url: Optional[bool] = None,
        include_source_ids: Optional[str | Iterable[str]] = None,
        exclude_source_ids: Optional[str | Iterable[str]] = None,
        min_citations: Optional[int] = None,
        max_citations: Optional[int] = None,
        min_authority_score: Optional[float] = None,
        max_authority_score: Optional[float] = None,
        min_relevance_score: Optional[float] = None,
        max_relevance_score: Optional[float] = None,
        min_hybrid_score: Optional[float] = None,
        max_hybrid_score: Optional[float] = None,
        min_recency_score: Optional[float] = None,
        max_recency_score: Optional[float] = None,
        recency_window_days: int = 730,
        recency_profile: Literal["strict", "balanced", "lenient"] = "balanced",
        as_of: Optional[datetime] = None,
        min_token_matches: Optional[int] = None,
        max_results_per_domain: Optional[int] = None,
        sort_by: Literal[
            "relevance",
            "hybrid",
            "title",
            "published_date",
            "citation_count",
            "authority",
            "recency",
        ] = "relevance",
    ) -> List[Source]:
        """Search sources with lightweight relevance ranking.

        Search is case-insensitive and matches across title, author,
        description, URL, and metadata fields.

        Args:
            query: Search text. Blank query returns all sources.
            source_type: Optional source type filter.
            source_types: Optional source type allow-list. Accepts a single
                source type or an iterable of source types. Cannot be used
                together with ``source_type``.
            exclude_source_types: Optional source type deny-list. Accepts a
                single source type or an iterable of source types. Matching
                source types are excluded even when they also appear in
                ``source_type``/``source_types`` filters.
            limit: Optional max number of results. Must be > 0 when set.
            offset: Optional zero-based number of ranked results to skip
                before returning results. Must be >= 0 when set.
            match_mode: Matching strategy. ``"all"`` requires every
                query token to appear in the searchable source text, ``"any"``
                returns sources that match at least one token, and
                ``"phrase"`` requires the normalized full query string to
                appear contiguously in searchable source text.
            published_after: Optional lower-bound date filter (inclusive).
            published_before: Optional upper-bound date filter (inclusive).
            min_age_days: Optional minimum source age in days relative to
                ``as_of`` (inclusive). When provided, undated sources are
                excluded because age cannot be determined.
            max_age_days: Optional maximum source age in days relative to
                ``as_of`` (inclusive). When provided, undated sources are
                excluded because age cannot be determined.
            metadata_filters: Optional metadata constraints where each key/value
                pair must match source metadata exactly (case-insensitive). Values
                may be scalars or iterables of accepted values.
            domains: Optional domain allow-list filter(s). Accepts a single
                domain string or an iterable of domains. Matching is
                case-insensitive and includes subdomains (e.g.
                ``news.example.com`` matches ``example.com``).
            exclude_domains: Optional domain deny-list filter(s). Sources whose
                hostnames match any configured domain (including subdomains)
                are excluded from results.
            has_url: Optional URL presence filter. ``True`` keeps only sources
                with URLs, ``False`` keeps only URL-less sources.
            include_source_ids: Optional source-id allow-list. When provided,
                only matching source IDs are considered.
            exclude_source_ids: Optional source-id deny-list. Matching source
                IDs are excluded even when also included via
                ``include_source_ids``.
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
            min_relevance_score: Optional inclusive lower bound for computed
                relevance score. Useful when filtering out weak lexical matches
                from broad ``match_mode='any'`` searches.
            max_relevance_score: Optional inclusive upper bound for computed
                relevance score. Useful when isolating weaker/secondary matches
                for fallback or diversity logic.
            min_hybrid_score: Optional inclusive lower bound for computed
                hybrid score. Useful for requiring a minimum blend of lexical
                relevance and source-quality signals.
            max_hybrid_score: Optional inclusive upper bound for computed
                hybrid score. Useful for isolating secondary matches for
                fallback ranking tiers.
            min_recency_score: Optional inclusive lower bound for computed
                recency score in the ``0.0`` to ``1.0`` range.
            max_recency_score: Optional inclusive upper bound for computed
                recency score in the ``0.0`` to ``1.0`` range.
            recency_window_days: Publication age window used for recency
                scoring when ``sort_by='recency'``.
            recency_profile: Recency sensitivity profile used when
                ``sort_by='recency'``. ``"strict"`` penalizes stale sources
                more aggressively, while ``"lenient"`` decays slower.
            as_of: Optional reference timestamp for deterministic recency
                calculations and age-day filters.
            min_token_matches: Optional minimum number of unique query tokens
                that must appear in a source's searchable text. Useful for
                reducing weak single-token matches when using
                ``match_mode='any'``. Ignored when the query is blank.
            max_results_per_domain: Optional cap for how many results can be
                returned per normalized domain bucket (case-insensitive and
                without ``www``). Subdomains are grouped using a lightweight
                eTLD+1 heuristic. Sources without parseable URLs are not capped.
            sort_by: Result ordering strategy. ``"relevance"`` favors textual
                score, ``"hybrid"`` blends relevance with authority,
                citation traction, and recency quality signals, ``"title"``
                sorts alphabetically, ``"published_date"`` sorts newest-first
                with undated sources last, ``"citation_count"`` prioritizes
                frequently cited sources, and ``"authority"`` ranks by source
                reliability heuristics based on source type (for example,
                databases before generic web pages). ``"recency"`` ranks by
                freshness score using
                ``recency_window_days``/``recency_profile``.

        Returns:
            Ranked list of matching sources.
        """
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if offset is not None:
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise ValueError("offset must be an integer")
            if offset < 0:
                raise ValueError("offset cannot be negative")

        if source_type is not None and source_types is not None:
            raise ValueError("source_type and source_types cannot be used together")

        if has_url is not None and not isinstance(has_url, bool):
            raise ValueError("has_url must be a boolean when provided")

        if (
            published_after is not None
            and published_before is not None
            and published_after > published_before
        ):
            raise ValueError("published_after cannot be later than published_before")

        if min_age_days is not None:
            if isinstance(min_age_days, bool) or not isinstance(min_age_days, int):
                raise ValueError("min_age_days must be an integer")
            if min_age_days < 0:
                raise ValueError("min_age_days cannot be negative")

        if max_age_days is not None:
            if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
                raise ValueError("max_age_days must be an integer")
            if max_age_days < 0:
                raise ValueError("max_age_days cannot be negative")

        if (
            min_age_days is not None
            and max_age_days is not None
            and min_age_days > max_age_days
        ):
            raise ValueError("min_age_days cannot be greater than max_age_days")

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

        if min_relevance_score is not None and min_relevance_score < 0:
            raise ValueError("min_relevance_score cannot be negative")

        if max_relevance_score is not None and max_relevance_score < 0:
            raise ValueError("max_relevance_score cannot be negative")

        if (
            min_relevance_score is not None
            and max_relevance_score is not None
            and min_relevance_score > max_relevance_score
        ):
            raise ValueError(
                "min_relevance_score cannot be greater than max_relevance_score"
            )

        if min_hybrid_score is not None and min_hybrid_score < 0:
            raise ValueError("min_hybrid_score cannot be negative")

        if max_hybrid_score is not None and max_hybrid_score < 0:
            raise ValueError("max_hybrid_score cannot be negative")

        if (
            min_hybrid_score is not None
            and max_hybrid_score is not None
            and min_hybrid_score > max_hybrid_score
        ):
            raise ValueError("min_hybrid_score cannot be greater than max_hybrid_score")

        if min_recency_score is not None and not 0 <= min_recency_score <= 1:
            raise ValueError("min_recency_score must be between 0 and 1")

        if max_recency_score is not None and not 0 <= max_recency_score <= 1:
            raise ValueError("max_recency_score must be between 0 and 1")

        if (
            min_recency_score is not None
            and max_recency_score is not None
            and min_recency_score > max_recency_score
        ):
            raise ValueError(
                "min_recency_score cannot be greater than max_recency_score"
            )

        if recency_window_days <= 0:
            raise ValueError("recency_window_days must be greater than 0")

        if recency_profile not in self.RECENCY_PROFILE_FACTORS:
            raise ValueError(
                "recency_profile must be one of: strict, balanced, lenient"
            )

        if min_token_matches is not None:
            if isinstance(min_token_matches, bool) or not isinstance(
                min_token_matches, int
            ):
                raise ValueError("min_token_matches must be an integer")
            if min_token_matches <= 0:
                raise ValueError("min_token_matches must be greater than 0")

        if max_results_per_domain is not None:
            if isinstance(max_results_per_domain, bool) or not isinstance(
                max_results_per_domain, int
            ):
                raise ValueError("max_results_per_domain must be an integer")
            if max_results_per_domain <= 0:
                raise ValueError("max_results_per_domain must be greater than 0")

        normalized_match_mode = self._normalize_text(match_mode)
        if normalized_match_mode not in {"all", "any", "phrase"}:
            raise ValueError("match_mode must be 'all', 'any', or 'phrase'")

        normalized_sort_by = (
            self._normalize_text(str(sort_by)).replace(" ", "_").replace("-", "_")
        )
        if normalized_sort_by not in {
            "relevance",
            "hybrid",
            "title",
            "published_date",
            "citation_count",
            "authority",
            "recency",
        }:
            raise ValueError(
                "sort_by must be one of: relevance, hybrid, title, published_date, citation_count, authority, recency"
            )

        normalized_query = self._normalize_text(query)
        query_tokens = [token for token in normalized_query.split(" ") if token]
        unique_query_tokens = list(dict.fromkeys(query_tokens))

        if (
            min_token_matches is not None
            and unique_query_tokens
            and min_token_matches > len(unique_query_tokens)
        ):
            raise ValueError(
                "min_token_matches cannot exceed number of unique query tokens"
            )

        normalized_source_types = self._normalize_source_types(
            source_types if source_types is not None else source_type,
            argument_name="source_types" if source_types is not None else "source_type",
        )
        normalized_exclude_source_types = self._normalize_source_types(
            exclude_source_types,
            argument_name="exclude_source_types",
        )

        normalized_metadata_filters = self._normalize_metadata_filters(metadata_filters)
        normalized_domains = self._normalize_domains(domains)
        normalized_exclude_domains = self._normalize_domains(exclude_domains)
        normalized_include_source_ids = self._normalize_source_ids(
            include_source_ids,
            argument_name="include_source_ids",
        )
        normalized_exclude_source_ids = self._normalize_source_ids(
            exclude_source_ids,
            argument_name="exclude_source_ids",
        )
        reference_time = self._normalize_datetime(
            as_of if as_of is not None else datetime.now(timezone.utc)
        )
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        ranked_matches: List[tuple[float, int, float, float, float, Source]] = []

        for source in self.sources.values():
            if (
                normalized_include_source_ids is not None
                and source.id not in normalized_include_source_ids
            ):
                continue

            if (
                normalized_exclude_source_ids is not None
                and source.id in normalized_exclude_source_ids
            ):
                continue

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
                normalized_source_types is not None
                and source_type_value not in normalized_source_types
            ):
                continue

            if (
                normalized_exclude_source_types is not None
                and source_type_value in normalized_exclude_source_types
            ):
                continue

            source_hostname = ""
            if source.url:
                source_hostname = self._normalize_domain(str(source.url))

            if (
                normalized_exclude_domains is not None
                and source_hostname
                and self._domain_matches_allowed(
                    source_hostname,
                    normalized_exclude_domains,
                )
            ):
                continue

            if normalized_domains is not None and (
                not source_hostname
                or not self._domain_matches_allowed(
                    source_hostname,
                    normalized_domains,
                )
            ):
                continue

            source_has_url = source.url is not None
            if has_url is True and not source_has_url:
                continue
            if has_url is False and source_has_url:
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

            source_age_days = self._compute_source_age_days(
                source.published_date,
                reference_time=reference_time,
            )
            if min_age_days is not None or max_age_days is not None:
                if source_age_days is None:
                    continue
                if min_age_days is not None and source_age_days < min_age_days:
                    continue
                if max_age_days is not None and source_age_days > max_age_days:
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
                elif normalized_match_mode == "any":
                    has_match = any(token in searchable_text for token in query_tokens)
                else:
                    has_match = normalized_query in searchable_text

                if not has_match:
                    continue

                if min_token_matches is not None:
                    token_match_count = sum(
                        token in searchable_text for token in unique_query_tokens
                    )
                    if token_match_count < min_token_matches:
                        continue

            score = self._compute_relevance_score(
                source,
                query_tokens=query_tokens,
                normalized_query=normalized_query,
            )

            if min_relevance_score is not None and score < min_relevance_score:
                continue

            if max_relevance_score is not None and score > max_relevance_score:
                continue

            recency_score = self._compute_recency_score(
                source.published_date,
                reference_time=reference_time,
                recency_window_days=recency_window_days,
                recency_profile=recency_profile,
            )
            hybrid_score = self._compute_hybrid_score(
                relevance_score=score,
                citation_count=citation_count,
                authority_score=authority_score,
                recency_score=recency_score,
            )

            if min_hybrid_score is not None and hybrid_score < min_hybrid_score:
                continue

            if max_hybrid_score is not None and hybrid_score > max_hybrid_score:
                continue

            if min_recency_score is not None and recency_score < min_recency_score:
                continue

            if max_recency_score is not None and recency_score > max_recency_score:
                continue

            ranked_matches.append(
                (
                    score,
                    citation_count,
                    authority_score,
                    recency_score,
                    hybrid_score,
                    source,
                )
            )

        if normalized_sort_by == "hybrid":
            ranked_matches.sort(
                key=lambda item: (
                    -item[4],
                    -item[0],
                    -item[1],
                    self._normalize_text(item[5].title),
                )
            )
        elif normalized_sort_by == "title":
            ranked_matches.sort(
                key=lambda item: (
                    self._normalize_text(item[5].title),
                    -item[0],
                    -item[1],
                )
            )
        elif normalized_sort_by == "published_date":
            ranked_matches.sort(
                key=lambda item: (
                    item[5].published_date is None,
                    -(
                        item[5].published_date.toordinal()
                        if item[5].published_date
                        else 0
                    ),
                    self._normalize_text(item[5].title),
                )
            )
        elif normalized_sort_by == "citation_count":
            ranked_matches.sort(
                key=lambda item: (
                    -item[1],
                    -item[0],
                    self._normalize_text(item[5].title),
                )
            )
        elif normalized_sort_by == "authority":
            ranked_matches.sort(
                key=lambda item: (
                    -item[2],
                    -item[0],
                    -item[1],
                    self._normalize_text(item[5].title),
                )
            )
        elif normalized_sort_by == "recency":
            ranked_matches.sort(
                key=lambda item: (
                    -item[3],
                    -item[0],
                    -item[1],
                    self._normalize_text(item[5].title),
                )
            )
        else:
            ranked_matches.sort(
                key=lambda item: (
                    -item[0],
                    -item[1],
                    self._normalize_text(item[5].title),
                )
            )

        sources = [source for *_, source in ranked_matches]

        if max_results_per_domain is not None:
            domain_counts: Counter[str] = Counter()
            diversity_capped_sources: List[Source] = []
            for source in sources:
                hostname = self._extract_source_hostname(source)
                if hostname is None:
                    diversity_capped_sources.append(source)
                    continue

                if domain_counts[hostname] >= max_results_per_domain:
                    continue

                domain_counts[hostname] += 1
                diversity_capped_sources.append(source)

            sources = diversity_capped_sources

        if offset is not None:
            sources = sources[offset:]

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
        source_types: Optional[SourceType | str | Iterable[SourceType | str]] = None,
        exclude_source_types: Optional[
            SourceType | str | Iterable[SourceType | str]
        ] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        match_mode: Literal["all", "any", "phrase"] = "all",
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None,
        min_age_days: Optional[int] = None,
        max_age_days: Optional[int] = None,
        metadata_filters: Optional[Mapping[str, Any]] = None,
        domains: Optional[str | Iterable[str]] = None,
        exclude_domains: Optional[str | Iterable[str]] = None,
        has_url: Optional[bool] = None,
        include_source_ids: Optional[str | Iterable[str]] = None,
        exclude_source_ids: Optional[str | Iterable[str]] = None,
        min_citations: Optional[int] = None,
        max_citations: Optional[int] = None,
        min_authority_score: Optional[float] = None,
        max_authority_score: Optional[float] = None,
        min_relevance_score: Optional[float] = None,
        max_relevance_score: Optional[float] = None,
        min_hybrid_score: Optional[float] = None,
        max_hybrid_score: Optional[float] = None,
        min_recency_score: Optional[float] = None,
        max_recency_score: Optional[float] = None,
        recency_window_days: int = 730,
        recency_profile: Literal["strict", "balanced", "lenient"] = "balanced",
        as_of: Optional[datetime] = None,
        min_token_matches: Optional[int] = None,
        max_results_per_domain: Optional[int] = None,
        sort_by: Literal[
            "relevance",
            "hybrid",
            "title",
            "published_date",
            "citation_count",
            "authority",
            "recency",
        ] = "relevance",
    ) -> List[Dict[str, Any]]:
        """Search sources and return explainable ranking metadata.

        This complements :meth:`search_sources` by exposing per-result details
        useful for UI debugging, audit logs, and ranking transparency.
        """
        matched_sources = self.search_sources(
            query,
            source_type=source_type,
            source_types=source_types,
            exclude_source_types=exclude_source_types,
            limit=limit,
            offset=offset,
            match_mode=match_mode,
            published_after=published_after,
            published_before=published_before,
            min_age_days=min_age_days,
            max_age_days=max_age_days,
            metadata_filters=metadata_filters,
            domains=domains,
            exclude_domains=exclude_domains,
            has_url=has_url,
            include_source_ids=include_source_ids,
            exclude_source_ids=exclude_source_ids,
            min_citations=min_citations,
            max_citations=max_citations,
            min_authority_score=min_authority_score,
            max_authority_score=max_authority_score,
            min_relevance_score=min_relevance_score,
            max_relevance_score=max_relevance_score,
            min_hybrid_score=min_hybrid_score,
            max_hybrid_score=max_hybrid_score,
            min_recency_score=min_recency_score,
            max_recency_score=max_recency_score,
            recency_window_days=recency_window_days,
            recency_profile=recency_profile,
            as_of=as_of,
            min_token_matches=min_token_matches,
            max_results_per_domain=max_results_per_domain,
            sort_by=sort_by,
        )

        normalized_query = self._normalize_text(query)
        query_tokens = [token for token in normalized_query.split(" ") if token]
        reference_time = self._normalize_datetime(
            as_of if as_of is not None else datetime.now(timezone.utc)
        )
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        detailed_matches: List[Dict[str, Any]] = []
        for index, source in enumerate(matched_sources, start=1):
            citation_count = citation_counts.get(source.id, 0)
            authority_score = self.SOURCE_AUTHORITY_WEIGHTS.get(
                source.type,
                0.5,
            )
            recency_score = self._compute_recency_score(
                source.published_date,
                reference_time=reference_time,
                recency_window_days=recency_window_days,
                recency_profile=recency_profile,
            )
            source_age_days = self._compute_source_age_days(
                source.published_date,
                reference_time=reference_time,
            )
            relevance_score = self._compute_relevance_score(
                source,
                query_tokens=query_tokens,
                normalized_query=normalized_query,
            )
            match_details = self._build_match_details(
                source,
                query_tokens=query_tokens,
                normalized_query=normalized_query,
            )
            detailed_matches.append(
                {
                    "rank": index,
                    "source": source,
                    "citation_count": citation_count,
                    "authority_score": authority_score,
                    "recency_score": recency_score,
                    "age_days": round(source_age_days, 3)
                    if source_age_days is not None
                    else None,
                    "relevance_score": relevance_score,
                    "hybrid_score": self._compute_hybrid_score(
                        relevance_score=relevance_score,
                        citation_count=citation_count,
                        authority_score=authority_score,
                        recency_score=recency_score,
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
            style: Citation style (apa, mla, chicago, harvard)
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

    @staticmethod
    def _normalize_identifier_batch(
        identifiers: str | Iterable[str],
        *,
        argument_name: str,
    ) -> list[str]:
        """Normalize batch identifier arguments for bulk delete helpers."""
        if isinstance(identifiers, str):
            raw_identifiers = [identifiers]
        else:
            raw_identifiers = list(identifiers)

        if not raw_identifiers:
            raise ValueError(f"{argument_name} must include at least one id")

        normalized_identifiers: list[str] = []
        seen: set[str] = set()

        for identifier in raw_identifiers:
            if not isinstance(identifier, str):
                raise ValueError(f"{argument_name} must contain only string ids")

            normalized_identifier = identifier.strip()
            if not normalized_identifier:
                raise ValueError(f"{argument_name} must contain non-empty ids")

            if normalized_identifier in seen:
                continue

            seen.add(normalized_identifier)
            normalized_identifiers.append(normalized_identifier)

        return normalized_identifiers

    def delete_citations(
        self,
        citation_ids: str | Iterable[str],
    ) -> Dict[str, bool]:
        """Delete multiple citations and return per-id removal status.

        Duplicate IDs are processed once in first-seen order.
        """
        normalized_citation_ids = self._normalize_identifier_batch(
            citation_ids,
            argument_name="citation_ids",
        )

        return {
            citation_id: self.delete_citation(citation_id)
            for citation_id in normalized_citation_ids
        }

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

    def delete_sources(
        self,
        source_ids: str | Iterable[str],
        *,
        cascade: bool = True,
    ) -> Dict[str, bool]:
        """Delete multiple sources and return per-id removal status.

        Duplicate IDs are processed once in first-seen order.
        """
        normalized_source_ids = self._normalize_identifier_batch(
            source_ids,
            argument_name="source_ids",
        )

        return {
            source_id: self.delete_source(source_id, cascade=cascade)
            for source_id in normalized_source_ids
        }

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
    def _compute_source_age_days(
        cls,
        published_date: Optional[datetime],
        *,
        reference_time: datetime,
    ) -> Optional[float]:
        """Compute source age in days relative to the provided reference time."""
        if published_date is None:
            return None

        normalized_published_date = cls._normalize_datetime(published_date)
        raw_age_days = (
            reference_time - normalized_published_date
        ).total_seconds() / 86400

        # Treat future publication timestamps as "fresh" for age filtering.
        return max(0.0, raw_age_days)

    @classmethod
    def _compute_recency_score(
        cls,
        published_date: Optional[datetime],
        *,
        reference_time: datetime,
        recency_window_days: int,
        recency_profile: Literal["strict", "balanced", "lenient"] = "balanced",
    ) -> float:
        """Compute recency freshness score for a single source."""
        if published_date is None:
            # Undated sources are penalized more heavily to encourage proper
            # publication metadata.
            return 0.3

        normalized_published_date = cls._normalize_datetime(published_date)
        raw_age_days = (
            reference_time - normalized_published_date
        ).total_seconds() / 86400

        # Handle future dates - sources with future publication dates are suspicious
        # and should be penalized similar to undated sources.
        if raw_age_days < 0:
            logger.warning(
                f"Source has future publication date: {published_date.isoformat()}"
            )
            return 0.3  # Same penalty as undated sources

        profile_factor = cls.RECENCY_PROFILE_FACTORS.get(recency_profile)
        if profile_factor is None:
            raise ValueError(
                "recency_profile must be one of: strict, balanced, lenient"
            )

        # Profile-specific multiplier allows consumers to tune how aggressively
        # publication age is penalized without changing the decay curve shape.
        age_days = raw_age_days * profile_factor

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
        recency_profile: Literal["strict", "balanced", "lenient"] = "balanced",
        as_of: Optional[datetime] = None,
        include_source_breakdown: bool = False,
        source_types: Optional[SourceType | str | Iterable[SourceType | str]] = None,
        domains: Optional[str | Iterable[str]] = None,
        include_source_ids: Optional[str | Iterable[str]] = None,
        exclude_source_ids: Optional[str | Iterable[str]] = None,
        cited_only: bool = False,
    ) -> Dict[str, Any]:
        """Generate a lightweight fact-check confidence report for current sources.

        The report uses deterministic heuristics so downstream consumers can show
        a trust score and explainability details without an additional LLM call.

        Args:
            min_sources: Minimum source count required for strong confidence.
            recency_window_days: Publication age window used for recency scoring.
            recency_profile: Recency sensitivity profile. ``"strict"`` penalizes
                stale sources more aggressively, ``"lenient"`` decays slower,
                and ``"balanced"`` keeps the default behavior.
            as_of: Optional reference timestamp for deterministic recency
                calculations. When omitted, uses current UTC time.
            include_source_breakdown: When ``True``, include per-source scoring
                details in ``source_breakdown`` for explainability/debugging.
            source_types: Optional source type allow-list. Accepts a single
                source type or iterable of source types.
            domains: Optional domain allow-list. Matching is case-insensitive
                and includes subdomains.
            include_source_ids: Optional source-id allow-list.
            exclude_source_ids: Optional source-id deny-list.
            cited_only: When ``True``, include only sources that are cited at
                least once in the current tracker.

        Returns:
            Dictionary with aggregate confidence score, level, gaps, and metrics.
        """
        if min_sources <= 0:
            raise ValueError("min_sources must be greater than 0")
        if recency_window_days <= 0:
            raise ValueError("recency_window_days must be greater than 0")
        if recency_profile not in self.RECENCY_PROFILE_FACTORS:
            raise ValueError(
                "recency_profile must be one of: strict, balanced, lenient"
            )
        if not isinstance(cited_only, bool):
            raise ValueError("cited_only must be a boolean")

        normalized_source_types = self._normalize_source_types(
            source_types,
            argument_name="source_types",
        )
        normalized_domains = self._normalize_domains(domains)
        normalized_include_source_ids = self._normalize_source_ids(
            include_source_ids,
            argument_name="include_source_ids",
        )
        normalized_exclude_source_ids = self._normalize_source_ids(
            exclude_source_ids,
            argument_name="exclude_source_ids",
        )

        reference_time = self._normalize_datetime(
            as_of if as_of is not None else datetime.now(timezone.utc)
        )
        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        scoped_sources: List[Source] = []
        for source in self.sources.values():
            if (
                normalized_include_source_ids is not None
                and source.id not in normalized_include_source_ids
            ):
                continue

            if (
                normalized_exclude_source_ids is not None
                and source.id in normalized_exclude_source_ids
            ):
                continue

            source_type_value = (
                source.type.value
                if isinstance(source.type, SourceType)
                else str(source.type)
            )
            normalized_source_type = self._normalize_text(source_type_value)
            if (
                normalized_source_types is not None
                and normalized_source_type not in normalized_source_types
            ):
                continue

            if normalized_domains is not None:
                if not source.url:
                    continue

                try:
                    source_hostname = self._normalize_domain(str(source.url))
                except ValueError:
                    continue

                if not self._domain_matches_allowed(
                    source_hostname,
                    normalized_domains,
                ):
                    continue

            if cited_only and citation_counts.get(source.id, 0) == 0:
                continue

            scoped_sources.append(source)

        total_sources = len(scoped_sources)
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
                    "total_available_sources": len(self.sources),
                    "filters_applied": any(
                        [
                            normalized_source_types,
                            normalized_domains,
                            normalized_include_source_ids,
                            normalized_exclude_source_ids,
                            cited_only,
                        ]
                    ),
                    "unique_domains": 0,
                    "cited_sources": 0,
                    "citation_coverage": 0.0,
                    "source_count_score": 0.0,
                    "domain_diversity_score": 0.0,
                    "authority_score": 0.0,
                    "recency_score": 0.0,
                    "recency_profile": recency_profile,
                },
            }
            if include_source_breakdown:
                report["source_breakdown"] = []
            return report

        cited_sources = sum(
            1 for source in scoped_sources if citation_counts.get(source.id, 0) > 0
        )
        citation_coverage = cited_sources / total_sources

        unique_domains = {
            parsed.hostname.casefold()
            for source in scoped_sources
            if source.url
            for parsed in [urlparse(str(source.url))]
            if parsed.hostname
        }

        authority_weights = []
        recency_scores = []
        source_breakdown: List[Dict[str, Any]] = []

        for source in scoped_sources:
            authority_score_for_source = self.SOURCE_AUTHORITY_WEIGHTS.get(
                source.type,
                0.5,
            )
            authority_weights.append(authority_score_for_source)

            source_recency_score = self._compute_recency_score(
                source.published_date,
                reference_time=reference_time,
                recency_window_days=recency_window_days,
                recency_profile=recency_profile,
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
                "total_available_sources": len(self.sources),
                "filters_applied": any(
                    [
                        normalized_source_types,
                        normalized_domains,
                        normalized_include_source_ids,
                        normalized_exclude_source_ids,
                        cited_only,
                    ]
                ),
                "unique_domains": len(unique_domains),
                "cited_sources": cited_sources,
                "citation_coverage": round(citation_coverage, 3),
                "source_count_score": round(source_count_score, 3),
                "domain_diversity_score": round(domain_diversity_score, 3),
                "authority_score": round(authority_score, 3),
                "recency_score": round(recency_score, 3),
                "recency_profile": recency_profile,
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

        total_sources = len(self.sources)
        total_citations = len(self.citations)
        avg_citations = total_citations / total_sources if total_sources else 0.0

        citation_counts = Counter(
            citation.source.id for citation in self.citations.values()
        )

        per_source_citation_counts = {
            source.id: citation_counts.get(source.id, 0)
            for source in self.sources.values()
        }

        source_count_items = list(per_source_citation_counts.items())

        least_cited = (
            min(
                source_count_items,
                key=lambda item: (
                    item[1],
                    self._normalize_text(self.sources[item[0]].title),
                    item[0],
                ),
            )
            if source_count_items
            else None
        )
        most_cited = (
            min(
                source_count_items,
                key=lambda item: (
                    -item[1],
                    self._normalize_text(self.sources[item[0]].title),
                    item[0],
                ),
            )
            if source_count_items
            else None
        )

        least_cited_source_id = least_cited[0] if least_cited else None
        least_cited_count = least_cited[1] if least_cited else 0
        most_cited_source_id = most_cited[0] if most_cited else None
        most_cited_count = most_cited[1] if most_cited else 0

        cited_source_count = sum(
            1 for count in per_source_citation_counts.values() if count > 0
        )
        uncited_source_count = total_sources - cited_source_count
        citation_coverage = cited_source_count / total_sources if total_sources else 0.0

        domain_rollups: dict[str, dict[str, int | str]] = {}
        for source in self.sources.values():
            hostname = self._extract_source_hostname(source)
            if hostname is None:
                continue

            citation_count_for_source = per_source_citation_counts.get(source.id, 0)
            rollup = domain_rollups.setdefault(
                hostname,
                {
                    "domain": hostname,
                    "source_count": 0,
                    "cited_source_count": 0,
                    "citation_count": 0,
                },
            )
            rollup["source_count"] += 1
            if citation_count_for_source > 0:
                rollup["cited_source_count"] += 1
            rollup["citation_count"] += citation_count_for_source

        total_domain_sources = sum(
            int(rollup["source_count"]) for rollup in domain_rollups.values()
        )
        total_domain_citations = sum(
            int(rollup["citation_count"]) for rollup in domain_rollups.values()
        )

        domain_breakdown = []
        for rollup in domain_rollups.values():
            source_count = int(rollup["source_count"])
            cited_count = int(rollup["cited_source_count"])
            citation_count = int(rollup["citation_count"])

            domain_breakdown.append(
                {
                    "domain": str(rollup["domain"]),
                    "source_count": source_count,
                    "cited_source_count": cited_count,
                    "uncited_source_count": source_count - cited_count,
                    "citation_count": citation_count,
                    "source_share": round(
                        source_count / total_domain_sources, 3
                    )
                    if total_domain_sources
                    else 0.0,
                    "citation_share": round(
                        citation_count / total_domain_citations, 3
                    )
                    if total_domain_citations
                    else 0.0,
                }
            )

        domain_breakdown.sort(
            key=lambda item: (
                -int(item["citation_count"]),
                -int(item["source_count"]),
                str(item["domain"]),
            )
        )

        most_cited_domain = domain_breakdown[0]["domain"] if domain_breakdown else None
        most_cited_domain_count = (
            domain_breakdown[0]["citation_count"] if domain_breakdown else 0
        )

        return {
            "total_sources": total_sources,
            "total_citations": total_citations,
            "average_citations_per_source": round(avg_citations, 2),
            "source_types": source_types,
            "unique_urls": len(self.source_url_map),
            "unique_source_fingerprints": len(self.source_fingerprint_map),
            "most_cited_source_id": most_cited_source_id,
            "most_cited_count": most_cited_count,
            "least_cited_source_id": least_cited_source_id,
            "least_cited_count": least_cited_count,
            "cited_source_count": cited_source_count,
            "uncited_source_count": uncited_source_count,
            "citation_coverage": round(citation_coverage, 3),
            "citation_counts_by_source": per_source_citation_counts,
            "domain_count": len(domain_breakdown),
            "most_cited_domain": most_cited_domain,
            "most_cited_domain_count": most_cited_domain_count,
            "domain_breakdown": domain_breakdown,
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
