"""Citation and Source Tracking service.

This module provides citation management and source tracking
for research and document generation agents.
"""

from app.services.citation.tracker import CitationTracker
from app.services.citation.models import Citation, Source, SourceType

__all__ = [
    "CitationTracker",
    "Citation",
    "Source",
    "SourceType",
]
