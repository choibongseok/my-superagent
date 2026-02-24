"""Agent Memory Timeline API — Idea #243.

User-facing endpoints to view, add, update, and delete agent memories.
Gives users transparency into what the AI remembers about them.

Endpoints:
  GET    /memory/timeline          → paginated memory timeline
  GET    /memory/search            → semantic search through memories
  POST   /memory                   → manually add a memory entry
  DELETE /memory/{memory_id}       → remove a specific memory
  GET    /memory/stats             → memory usage statistics
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.memory.manager import MemoryManager
from app.models.user import User

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """A single memory item in the timeline."""

    content: str
    score: Optional[float] = None
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    source: Optional[str] = None  # e.g. "research", "docs", "user", "conversation"
    agent_type: Optional[str] = None


class MemoryTimelineResponse(BaseModel):
    """Paginated memory timeline."""

    memories: list[MemoryEntry]
    total: int
    has_more: bool


class MemoryCreateRequest(BaseModel):
    """User-created memory entry."""

    content: str = Field(
        ..., min_length=1, max_length=2000,
        description="Memory content (e.g. 'Always write in Korean')",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Optional metadata tags",
    )


class MemoryCreateResponse(BaseModel):
    """Response after creating a memory."""

    memory_id: Optional[str] = None
    content: str
    created_at: str


class MemoryStatsResponse(BaseModel):
    """Memory usage statistics for the user."""

    conversation_turns: int
    long_term_memories: int
    oldest_memory: Optional[str] = None
    newest_memory: Optional[str] = None
    top_topics: list[str] = Field(default_factory=list)


class MemorySearchResponse(BaseModel):
    """Semantic search results."""

    results: list[MemoryEntry]
    query: str
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_memory_manager(user: User) -> MemoryManager:
    """Create a MemoryManager scoped to the user."""
    return MemoryManager(
        user_id=str(user.id),
        session_id=f"timeline-{user.id}",
    )


def _memory_to_entry(mem: dict) -> MemoryEntry:
    """Convert a raw memory dict to a MemoryEntry."""
    metadata = mem.get("metadata", {})
    return MemoryEntry(
        content=mem.get("content", mem.get("page_content", "")),
        score=mem.get("score"),
        metadata=metadata,
        created_at=metadata.get("created_at"),
        source=metadata.get("source", metadata.get("type")),
        agent_type=metadata.get("agent_type"),
    )


# ---------------------------------------------------------------------------
# GET /memory/timeline — chronological memory feed
# ---------------------------------------------------------------------------

@router.get(
    "/timeline",
    response_model=MemoryTimelineResponse,
    tags=["memory"],
    summary="View agent memory timeline (#243)",
)
async def get_memory_timeline(
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    after: Optional[str] = Query(None, description="ISO timestamp: only memories after this"),
    before: Optional[str] = Query(None, description="ISO timestamp: only memories before this"),
):
    """Return a paginated, reverse-chronological view of the user's memories.

    This is the 'what does AI know about me?' view.
    """
    manager = _get_memory_manager(current_user)

    # Use a broad search to fetch timeline entries
    filter_dict = {}
    if agent_type:
        filter_dict["agent_type"] = agent_type

    try:
        results = manager.search_memory(
            query="*",  # broad match
            k=page_size + 1,  # one extra row to detect whether a next page exists
            score_threshold=None,
            adaptive_threshold=False,
            filter_dict=filter_dict if filter_dict else None,
            sort_by_score=False,
            created_after=after,
            created_before=before,
            offset=(page - 1) * page_size,
        )
    except Exception as e:
        logger.warning(f"Memory timeline fetch failed: {e}")
        results = []

    # Accurate total via vector metadata scan (bounded by filter/date criteria)
    try:
        total = manager.count_memories(
            filter_dict=filter_dict if filter_dict else None,
            created_after=after,
            created_before=before,
        )
    except Exception as e:
        logger.warning(f"Memory timeline count failed: {e}")
        total = len(results)

    has_more = len(results) > page_size

    memories = [_memory_to_entry(r) for r in results[:page_size]]

    return MemoryTimelineResponse(
        memories=memories,
        total=total,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# GET /memory/search — semantic search
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=MemorySearchResponse,
    tags=["memory"],
    summary="Search agent memories semantically",
)
async def search_memories(
    current_user: Annotated[User, Depends(get_current_user)],
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    agent_type: Optional[str] = Query(None),
):
    """Semantic search through agent memories.

    Returns the most relevant memories matching the query.
    """
    manager = _get_memory_manager(current_user)

    filter_dict = {}
    if agent_type:
        filter_dict["agent_type"] = agent_type

    try:
        results = manager.search_memory(
            query=q,
            k=limit,
            score_threshold=0.5,
            filter_dict=filter_dict if filter_dict else None,
            sort_by_score=True,
            unique_content=True,
        )
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        results = []

    return MemorySearchResponse(
        results=[_memory_to_entry(r) for r in results],
        query=q,
        total=len(results),
    )


# ---------------------------------------------------------------------------
# POST /memory — user adds a memory
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=MemoryCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["memory"],
    summary="Add a user-defined memory (#243)",
)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Manually add a memory entry (e.g. 'Always write reports in Korean').

    User-defined memories are stored with source='user' and can be
    used by agents to personalize responses.
    """
    manager = _get_memory_manager(current_user)

    now = datetime.now(tz=timezone.utc).isoformat()
    metadata = {
        "source": "user",
        "type": "user_preference",
        "created_at": now,
        "user_id": str(current_user.id),
        **(body.metadata or {}),
    }

    memory_id = manager.add_memory(content=body.content, metadata=metadata)

    if memory_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory storage is not available. Check vector store configuration.",
        )

    return MemoryCreateResponse(
        memory_id=memory_id,
        content=body.content,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# DELETE /memory/{memory_id} — remove a memory
# ---------------------------------------------------------------------------

@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["memory"],
    summary="Delete a specific memory entry",
)
async def delete_memory(
    memory_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Remove a memory from the agent's knowledge about this user.

    Useful for correcting wrong assumptions or removing outdated info.
    """
    manager = _get_memory_manager(current_user)

    if not manager.vector_memory:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory storage is not available",
        )

    try:
        deleted = manager.vector_memory.delete_memory(memory_id)
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory not found or could not be deleted: {e}",
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )


# ---------------------------------------------------------------------------
# GET /memory/stats — usage overview
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    tags=["memory"],
    summary="Get memory usage statistics",
)
async def get_memory_stats(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Overview of how much the agent remembers about this user."""
    manager = _get_memory_manager(current_user)

    # Conversation turns
    turn_count = manager.get_turn_count()

    # Long-term memories — do a count + bounded metadata sample
    long_term_count = 0
    oldest = None
    newest = None
    top_topics: list[str] = []

    try:
        if getattr(manager, "vector_memory", None) and hasattr(
            manager.vector_memory, "get_memory_count"
        ):
            long_term_count = manager.vector_memory.get_memory_count()
        else:
            long_term_count = manager.count_memories()
    except Exception as e:
        logger.warning(f"Memory stats count failed: {e}")

    try:
        # Pull a bounded sample for metadata stats to avoid expensive full scans.
        all_memories = manager.search_memory(
            query="*",
            k=min(long_term_count or 200, 200),
            score_threshold=None,
            adaptive_threshold=False,
        ) if long_term_count else []

        # Extract timestamps and topics
        timestamps: list[str] = []
        agent_types: dict[str, int] = {}

        for m in all_memories:
            meta = m.get("metadata", {})
            ts = meta.get("created_at")
            if ts:
                timestamps.append(ts)
            at = meta.get("agent_type") or meta.get("source")
            if at:
                agent_types[at] = agent_types.get(at, 0) + 1

        if timestamps:
            timestamps.sort()
            oldest = timestamps[0]
            newest = timestamps[-1]

        # Top topics = most common agent_types/sources
        top_topics = sorted(agent_types, key=agent_types.get, reverse=True)[:5]

    except Exception as e:
        logger.warning(f"Memory stats fetch failed: {e}")

    return MemoryStatsResponse(
        conversation_turns=turn_count,
        long_term_memories=long_term_count,
        oldest_memory=oldest,
        newest_memory=newest,
        top_topics=top_topics,
    )
