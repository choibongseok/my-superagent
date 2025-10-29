"""Citation and Source data models."""

from enum import Enum
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
            style: Citation style (apa, mla, chicago)

        Returns:
            Formatted citation string
        """
        if style == "apa":
            return self._format_apa()
        elif style == "mla":
            return self._format_mla()
        elif style == "chicago":
            return self._format_chicago()
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

    def _format_mla(self) -> str:
        """Format in MLA style."""
        parts = []

        # Author. "Title." URL. Accessed Date.
        if self.author:
            parts.append(f"{self.author}.")

        parts.append(f'"{self.title}."')

        if self.url:
            parts.append(f"{self.url}.")

        accessed = self.accessed_date.strftime("%d %B %Y")
        parts.append(f"Accessed {accessed}.")

        return " ".join(parts)

    def _format_chicago(self) -> str:
        """Format in Chicago style."""
        parts = []

        # Author. "Title." Accessed Date. URL.
        if self.author:
            parts.append(f"{self.author}.")

        parts.append(f'"{self.title}."')

        accessed = self.accessed_date.strftime("%B %d, %Y")
        parts.append(f"Accessed {accessed}.")

        if self.url:
            parts.append(f"{self.url}.")

        return " ".join(parts)

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

    def to_inline_citation(self, style: str = "apa") -> str:
        """
        Format as inline citation.

        Args:
            style: Citation style

        Returns:
            Inline citation string
        """
        if style == "apa":
            if self.source.author and self.source.published_date:
                year = self.source.published_date.year
                return f"({self.source.author}, {year})"
            elif self.source.author:
                return f"({self.source.author})"
            else:
                return f"({self.source.title})"

        elif style == "mla":
            if self.source.author:
                if self.page_number:
                    return f"({self.source.author} {self.page_number})"
                return f"({self.source.author})"
            else:
                return f'("{self.source.title}")'

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
