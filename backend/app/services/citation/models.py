"""Citation and Source data models."""

from enum import Enum
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field


class SourceType(str, Enum):
    """Type of information source."""

    WEB = "web"
    DOCUMENT = "document"
    API = "api"
    DATABASE = "database"
    BOOK = "book"
    ARTICLE = "article"
    VIDEO = "video"
    OTHER = "other"


class Source(BaseModel):
    """Information source model."""

    id: str = Field(..., description="Unique source identifier")
    type: SourceType = Field(..., description="Type of source")
    title: str = Field(..., description="Source title")
    url: Optional[HttpUrl] = Field(None, description="Source URL")
    author: Optional[str] = Field(None, description="Author name")
    published_date: Optional[datetime] = Field(None, description="Publication date")
    accessed_date: datetime = Field(
        default_factory=datetime.utcnow, description="Date accessed"
    )
    description: Optional[str] = Field(None, description="Source description")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        use_enum_values = True

    def to_citation_format(self, style: str = "apa") -> str:
        """
        Format source as citation string.

        Args:
            style: Citation style (apa, mla, chicago, harvard, vancouver, ieee, bibtex)

        Returns:
            Formatted citation string
        """
        normalized_style = style.strip().lower()

        if normalized_style == "apa":
            return self._format_apa()
        elif normalized_style == "mla":
            return self._format_mla()
        elif normalized_style == "chicago":
            return self._format_chicago()
        elif normalized_style == "harvard":
            return self._format_harvard()
        elif normalized_style == "vancouver":
            return self._format_vancouver()
        elif normalized_style == "ieee":
            return self._format_ieee()
        elif normalized_style in {"bibtex", "bib"}:
            return self._format_bibtex()
        else:
            return self._format_simple()

    def _format_apa(self) -> str:
        """Format in APA style."""
        parts = []

        # Author (Year). Title. URL
        if self.author:
            parts.append(f"{self.author}.")

        if self.published_date:
            year = self.published_date.year
            parts.append(f"({year}).")

        parts.append(f"{self.title}.")

        if self.url:
            parts.append(f"Retrieved from {self.url}")

        return " ".join(parts)

    @staticmethod
    def _quoted_title(title: str) -> str:
        """Return title wrapped in quotes with terminal punctuation outside quotes."""
        normalized = title.strip().rstrip(".")
        return f'"{normalized}".'

    def _format_mla(self) -> str:
        """Format in MLA style."""
        parts = []

        # Author. "Title". URL. Accessed Date.
        if self.author:
            parts.append(f"{self.author}.")

        parts.append(self._quoted_title(self.title))

        if self.url:
            parts.append(f"{self.url}.")

        accessed = self.accessed_date.strftime("%d %B %Y")
        parts.append(f"Accessed {accessed}.")

        return " ".join(parts)

    def _format_chicago(self) -> str:
        """Format in Chicago style."""
        parts = []

        # Author. "Title". Accessed Date. URL.
        if self.author:
            parts.append(f"{self.author}.")

        parts.append(self._quoted_title(self.title))

        accessed = self.accessed_date.strftime("%B %d, %Y")
        parts.append(f"Accessed {accessed}.")

        if self.url:
            parts.append(f"{self.url}.")

        return " ".join(parts)

    def _format_harvard(self) -> str:
        """Format in Harvard style."""
        parts = []

        year = str(self.published_date.year) if self.published_date else "n.d."

        if self.author:
            parts.append(f"{self.author} ({year}).")
            parts.append(f"{self.title}.")
        else:
            parts.append(f"{self.title} ({year}).")

        if self.url:
            parts.append(f"Available at: {self.url}.")

        accessed = self.accessed_date.strftime("%d %B %Y")
        parts.append(f"Accessed {accessed}.")

        return " ".join(parts)

    def _format_vancouver(self) -> str:
        """Format in Vancouver style."""
        parts = []

        if self.author:
            parts.append(f"{self.author}.")

        parts.append(f"{self.title}.")

        if self.published_date:
            parts.append(f"{self.published_date.year}.")

        if self.url:
            parts.append(f"Available from: {self.url}.")
            accessed = self.accessed_date.strftime("%Y %b %d")
            parts.append(f"[cited {accessed}].")

        return " ".join(parts)

    def _format_ieee(self) -> str:
        """Format in IEEE style for online/web references."""
        parts = []

        if self.author:
            parts.append(f"{self.author},")

        parts.append(f'"{self.title},"')

        if self.published_date:
            parts.append(f"{self.published_date.year}.")

        if self.url:
            parts.append(f"[Online]. Available: {self.url}.")
            accessed = self.accessed_date.strftime("%b %d, %Y")
            parts.append(f"[Accessed: {accessed}].")

        return " ".join(parts)

    @staticmethod
    def _escape_bibtex_value(value: str) -> str:
        """Escape special characters for safe BibTeX field values."""
        return (
            value.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\n", " ")
        )

    @staticmethod
    def _sanitize_bibtex_key_component(value: str) -> str:
        """Normalize strings into lowercase alphanumeric BibTeX key parts."""
        return re.sub(r"[^0-9a-z]+", "", value.casefold())

    @classmethod
    def _default_bibtex_key_author_token(
        cls, author: Optional[str], source_id: str
    ) -> str:
        """Resolve deterministic author token used for BibTeX citation keys."""
        if author:
            normalized_author = author.strip()
            if "," in normalized_author:
                candidate = normalized_author.split(",", maxsplit=1)[0].strip()
            else:
                candidate = normalized_author.split()[-1] if normalized_author else ""

            normalized_candidate = cls._sanitize_bibtex_key_component(candidate)
            if normalized_candidate:
                return normalized_candidate

        fallback_id = cls._sanitize_bibtex_key_component(source_id)
        return fallback_id or "source"

    @classmethod
    def _default_bibtex_key_title_token(cls, title: str) -> str:
        """Resolve deterministic title token used for BibTeX citation keys."""
        for token in re.findall(r"[A-Za-z0-9]+", title):
            normalized_token = cls._sanitize_bibtex_key_component(token)
            if normalized_token:
                return normalized_token

        return "reference"

    def to_bibtex_key(self) -> str:
        """Return deterministic citation key used by BibTeX outputs."""
        author_token = self._default_bibtex_key_author_token(self.author, self.id)
        year_token = str(self.published_date.year) if self.published_date else "nd"
        title_token = self._default_bibtex_key_title_token(self.title)
        return f"{author_token}{year_token}{title_token}"

    @staticmethod
    def _bibtex_entry_type(source_type: SourceType) -> str:
        """Map source types to BibTeX entry kinds."""
        if source_type == SourceType.BOOK:
            return "book"
        if source_type == SourceType.ARTICLE:
            return "article"

        return "misc"

    def _format_bibtex(self) -> str:
        """Format source as a BibTeX entry for LaTeX workflows."""
        fields: list[tuple[str, str]] = [("title", self.title)]

        if self.author:
            fields.append(("author", self.author))

        if self.published_date:
            fields.append(("year", str(self.published_date.year)))

        if self.url:
            fields.append(("url", str(self.url)))

        fields.append(("urldate", self.accessed_date.strftime("%Y-%m-%d")))

        if self.description:
            fields.append(("note", self.description))

        serialized_fields = ",\n".join(
            f"  {field_name} = {{{self._escape_bibtex_value(field_value)}}}"
            for field_name, field_value in fields
        )

        return (
            f"@{self._bibtex_entry_type(self.type)}"
            f"{{{self.to_bibtex_key()},\n"
            f"{serialized_fields}\n"
            "}"
        )

    def _format_simple(self) -> str:
        """Simple format with basic info."""
        parts = [self.title]

        if self.author:
            parts.append(f"by {self.author}")

        if self.url:
            parts.append(f"({self.url})")

        return " ".join(parts)


class Citation(BaseModel):
    """Citation reference model."""

    id: str = Field(..., description="Unique citation identifier")
    source: Source = Field(..., description="Referenced source")
    quoted_text: Optional[str] = Field(None, description="Quoted text from source")
    page_number: Optional[int] = Field(None, description="Page number")
    location: Optional[str] = Field(None, description="Location in document")
    context: Optional[str] = Field(None, description="Context of citation")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Citation creation time"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @staticmethod
    def _vancouver_label(identifier: str) -> str:
        """Extract numeric labels from citation ids for Vancouver-style inlines."""
        match = re.search(r"(\d+)$", identifier)
        if match:
            return match.group(1)

        return identifier

    def to_inline_citation(self, style: str = "apa") -> str:
        """
        Format as inline citation.

        Args:
            style: Citation style (apa, mla, harvard, vancouver, ieee, bibtex)

        Returns:
            Inline citation string
        """
        normalized_style = style.strip().lower()

        if normalized_style == "apa":
            if self.source.author and self.source.published_date:
                year = self.source.published_date.year
                return f"({self.source.author}, {year})"
            elif self.source.author:
                return f"({self.source.author})"
            else:
                return f"({self.source.title})"

        elif normalized_style == "mla":
            if self.source.author:
                if self.page_number:
                    return f"({self.source.author} {self.page_number})"
                return f"({self.source.author})"
            else:
                return f'("{self.source.title}")'

        elif normalized_style == "harvard":
            year = (
                str(self.source.published_date.year)
                if self.source.published_date
                else "n.d."
            )
            if self.source.author:
                return f"({self.source.author}, {year})"
            return f"({self.source.title}, {year})"

        elif normalized_style in {"vancouver", "ieee"}:
            return f"[{self._vancouver_label(self.id)}]"

        elif normalized_style in {"bibtex", "bib"}:
            return f"\\cite{{{self.source.to_bibtex_key()}}}"

        else:
            # Simple numbered citation
            return f"[{self.id}]"

    def to_full_citation(self, style: str = "apa") -> str:
        """
        Format as full citation.

        Args:
            style: Citation style

        Returns:
            Full citation string
        """
        return self.source.to_citation_format(style=style)


__all__ = ["Source", "Citation", "SourceType"]
