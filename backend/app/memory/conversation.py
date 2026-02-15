"""Conversation Memory implementation for multi-turn dialogues.

This module provides conversation buffer memory management for maintaining
context across multiple turns in agent conversations.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Literal, Optional
from datetime import datetime

from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Manages conversation memory for multi-turn dialogues.

    Features:
        - Conversation buffer for short-term memory
        - Automatic summarization for long conversations
        - Token limit management
        - Message filtering and retrieval

    Usage:
        memory = ConversationMemory(user_id="user123", session_id="session456")
        memory.add_user_message("Hello, how are you?")
        memory.add_ai_message("I'm doing well, thank you!")

        messages = memory.get_messages()
        context = memory.get_context()
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        max_token_limit: int = 2000,
        use_summary: bool = False,
        llm: Optional[ChatOpenAI] = None,
    ):
        """
        Initialize conversation memory.

        Args:
            user_id: User identifier
            session_id: Session identifier
            max_token_limit: Maximum tokens to keep in memory
            use_summary: Use summarization for long conversations
            llm: LLM instance for summarization
        """
        self.user_id = user_id
        self.session_id = session_id
        self.max_token_limit = max_token_limit
        self.use_summary = use_summary

        # Initialize memory backend
        if use_summary and llm:
            self.memory = ConversationSummaryMemory(
                llm=llm,
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=max_token_limit,
            )
        else:
            self.memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=max_token_limit,
            )

        # Metadata
        self.metadata: Dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "turn_count": 0,
        }

        logger.info(
            f"ConversationMemory initialized for user={user_id}, "
            f"session={session_id}, summary={use_summary}"
        )

    def add_user_message(self, message: str) -> None:
        """
        Add user message to conversation history.

        Args:
            message: User message content
        """
        self.memory.chat_memory.add_message(HumanMessage(content=message))
        self.metadata["turn_count"] += 1
        self.metadata["last_user_message"] = message
        self.metadata["last_updated"] = datetime.utcnow().isoformat()

        logger.debug(f"Added user message to session {self.session_id}")

    def add_ai_message(self, message: str) -> None:
        """
        Add AI message to conversation history.

        Args:
            message: AI message content
        """
        self.memory.chat_memory.add_message(AIMessage(content=message))
        self.metadata["last_ai_message"] = message
        self.metadata["last_updated"] = datetime.utcnow().isoformat()

        logger.debug(f"Added AI message to session {self.session_id}")

    def add_system_message(self, message: str) -> None:
        """
        Add system message to conversation history.

        Args:
            message: System message content
        """
        self.memory.chat_memory.add_message(SystemMessage(content=message))
        self.metadata["last_system_message"] = message
        self.metadata["last_updated"] = datetime.utcnow().isoformat()

        logger.debug(f"Added system message to session {self.session_id}")

    def add_messages(self, messages: List[BaseMessage]) -> None:
        """
        Add multiple messages to conversation history.

        Args:
            messages: List of messages to add
        """
        for message in messages:
            self.memory.chat_memory.add_message(message)
            if isinstance(message, HumanMessage):
                self.metadata["turn_count"] += 1

        self.metadata["last_updated"] = datetime.utcnow().isoformat()
        logger.debug(f"Added {len(messages)} messages to session {self.session_id}")

    def get_messages(self, last_n: Optional[int] = None) -> List[BaseMessage]:
        """
        Get conversation messages.

        Args:
            last_n: Number of recent messages to retrieve (None for all)

        Returns:
            List of conversation messages
        """
        messages = self.memory.chat_memory.messages

        if last_n is not None:
            messages = messages[-last_n:]

        return messages

    @staticmethod
    def _normalize_role_filter(
        role: str | Iterable[str],
    ) -> Optional[set[str]]:
        """Normalize role filters used by message search.

        Args:
            role: Either a single role (``"human"``), a comma-separated role
                string (``"human,ai"``), or an iterable of role strings.

        Returns:
            ``None`` when all roles should be included (``"any"``), otherwise
            a set of normalized role keys.

        Raises:
            ValueError: If provided roles are invalid.
        """
        normalized_roles: set[str] = set()

        if isinstance(role, str):
            raw_roles: Iterable[str] = role.split(",") if "," in role else [role]
        else:
            raw_roles = role

        for raw_role in raw_roles:
            if not isinstance(raw_role, str):
                raise ValueError("role must be one of: any, human, ai, system")

            normalized_role = raw_role.strip().lower()
            if not normalized_role:
                raise ValueError("role must be one of: any, human, ai, system")

            if normalized_role == "any":
                return None

            if normalized_role not in {"human", "ai", "system"}:
                raise ValueError("role must be one of: any, human, ai, system")

            normalized_roles.add(normalized_role)

        if not normalized_roles:
            raise ValueError("role must be one of: any, human, ai, system")

        return normalized_roles

    def search_messages(
        self,
        query: str,
        role: str | Iterable[str] = "any",
        *,
        case_sensitive: bool = False,
        last_n: Optional[int] = None,
        limit: Optional[int] = None,
        match_mode: Literal[
            "substring",
            "exact",
            "starts_with",
            "ends_with",
            "word",
            "regex",
            "fuzzy",
            "all_terms",
            "any_terms",
        ] = "substring",
        fuzzy_threshold: float = 0.75,
    ) -> List[BaseMessage]:
        """Search conversation messages by query text and optional role.

        Args:
            query: Query string used for matching message content
            role: Restrict results to role(s): "human", "ai", "system", or
                "any". Accepts a single value, comma-separated values, or an
                iterable of roles.
            case_sensitive: Whether to match query with exact case
            last_n: Restrict search to the last N messages
            limit: Maximum number of matched messages to return
            match_mode: Matching strategy:
                - "substring": query appears anywhere in content (default)
                - "exact": query must match the full message content
                - "starts_with": content begins with query text
                - "ends_with": content ends with query text
                - "word": query matches whole-word boundaries
                - "regex": query is treated as a regular expression
                - "fuzzy": typo-tolerant matching using similarity ratio
                - "all_terms": all query terms appear in any order
                - "any_terms": at least one query term appears
            fuzzy_threshold: Similarity threshold used by fuzzy matching (0-1)

        Returns:
            List of matched messages in chronological order

        Raises:
            ValueError: If query/role/limit/match_mode/fuzzy_threshold is invalid
        """
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string")

        normalized_roles = self._normalize_role_filter(role)

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        normalized_match_mode = match_mode.lower()
        if normalized_match_mode not in {
            "substring",
            "exact",
            "starts_with",
            "ends_with",
            "word",
            "regex",
            "fuzzy",
            "all_terms",
            "any_terms",
        }:
            raise ValueError(
                "match_mode must be one of: "
                "substring, exact, starts_with, ends_with, word, regex, "
                "fuzzy, all_terms, any_terms"
            )

        if not (0.0 <= fuzzy_threshold <= 1.0):
            raise ValueError("fuzzy_threshold must be in [0, 1]")

        target_query = normalized_query if case_sensitive else normalized_query.lower()
        regex_pattern: Optional[re.Pattern[str]] = None
        query_terms: Optional[List[str]] = None

        if normalized_match_mode == "word":
            flags = 0 if case_sensitive else re.IGNORECASE
            regex_pattern = re.compile(rf"\b{re.escape(normalized_query)}\b", flags)
        elif normalized_match_mode == "regex":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex_pattern = re.compile(normalized_query, flags)
            except re.error as error:
                raise ValueError(f"invalid regular expression: {error}") from error
        elif normalized_match_mode in {"all_terms", "any_terms"}:
            query_terms = self._tokenize_for_term_match(target_query)
            if not query_terms:
                raise ValueError(
                    "query must include at least one searchable term for "
                    "all_terms/any_terms match mode"
                )

        matches: List[BaseMessage] = []
        for message in self.get_messages(last_n=last_n):
            if normalized_roles is not None:
                message_role = self._get_role_key(message)
                if message_role not in normalized_roles:
                    continue

            content = str(message.content)
            searchable_content = content if case_sensitive else content.lower()

            if normalized_match_mode == "substring":
                is_match = target_query in searchable_content
            elif normalized_match_mode == "exact":
                is_match = searchable_content == target_query
            elif normalized_match_mode == "starts_with":
                is_match = searchable_content.startswith(target_query)
            elif normalized_match_mode == "ends_with":
                is_match = searchable_content.endswith(target_query)
            elif normalized_match_mode in {"word", "regex"}:
                # regex_pattern is guaranteed for "word" and "regex" modes.
                is_match = bool(regex_pattern and regex_pattern.search(content))
            elif normalized_match_mode in {"all_terms", "any_terms"}:
                # query_terms is guaranteed for term-based modes.
                candidate_terms = query_terms or []
                if normalized_match_mode == "all_terms":
                    is_match = all(
                        term in searchable_content for term in candidate_terms
                    )
                else:
                    is_match = any(
                        term in searchable_content for term in candidate_terms
                    )
            else:
                is_match = self._fuzzy_match(
                    query=normalized_query,
                    content=content,
                    case_sensitive=case_sensitive,
                    threshold=fuzzy_threshold,
                )

            if is_match:
                matches.append(message)

                if limit is not None and len(matches) >= limit:
                    break

        return matches

    @staticmethod
    def _tokenize_for_fuzzy_match(text: str) -> List[str]:
        """Return lowercase-ish word tokens used by fuzzy matching."""
        return re.findall(r"\w+", text)

    @staticmethod
    def _tokenize_for_term_match(text: str) -> List[str]:
        """Return normalized terms for all_terms/any_terms search modes."""
        return re.findall(r"\w+", text)

    @classmethod
    def _fuzzy_match(
        cls,
        *,
        query: str,
        content: str,
        case_sensitive: bool,
        threshold: float,
    ) -> bool:
        """Determine if content approximately matches query using token windows."""
        normalized_query = query if case_sensitive else query.lower()
        normalized_content = content if case_sensitive else content.lower()

        # Fast path for exact containment.
        if normalized_query in normalized_content:
            return True

        query_tokens = cls._tokenize_for_fuzzy_match(normalized_query)
        content_tokens = cls._tokenize_for_fuzzy_match(normalized_content)

        if not query_tokens or not content_tokens:
            return False

        window_size = len(query_tokens)
        if window_size == 1:
            candidates = content_tokens
        elif len(content_tokens) < window_size:
            candidates = [" ".join(content_tokens)]
        else:
            candidates = [
                " ".join(content_tokens[index : index + window_size])
                for index in range(len(content_tokens) - window_size + 1)
            ]

        max_similarity = max(
            SequenceMatcher(None, normalized_query, candidate).ratio()
            for candidate in candidates
        )
        return max_similarity >= threshold

    def get_context(self) -> str:
        """
        Get conversation context as formatted string.

        Returns:
            Formatted conversation history
        """
        messages = self.get_messages()

        context_parts = []
        for msg in messages:
            role = self._get_role_label(msg)
            context_parts.append(f"{role}: {msg.content}")

        return "\n".join(context_parts)

    def get_summary(self) -> Optional[str]:
        """
        Get conversation summary (if using summary memory).

        Returns:
            Summary string or None
        """
        if isinstance(self.memory, ConversationSummaryMemory):
            return self.memory.buffer
        return None

    def clear(self) -> None:
        """Clear all conversation history."""
        self.memory.clear()
        self.metadata["turn_count"] = 0
        self.metadata["cleared_at"] = datetime.utcnow().isoformat()

        logger.info(f"Cleared memory for session {self.session_id}")

    def get_turn_count(self) -> int:
        """
        Get number of conversation turns.

        Returns:
            Turn count
        """
        return self.metadata.get("turn_count", 0)

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get conversation metadata.

        Returns:
            Metadata dictionary
        """
        return self.metadata.copy()

    @property
    def langchain_memory(self):
        """
        Get the underlying LangChain memory object for agent integration.

        Returns:
            ConversationBufferMemory or ConversationSummaryMemory instance
        """
        return self.memory

    @property
    def buffer(self):
        """
        LangChain agent가 접근할 수 있도록 buffer 속성 노출.

        BaseAgent와 MemoryManager에서 self.memory.buffer로 접근 가능.

        Returns:
            LangChain memory object
        """
        return self.memory

    @staticmethod
    def _get_role_key(message: BaseMessage) -> str:
        """Return a stable role key for a LangChain message."""
        if isinstance(message, HumanMessage):
            return "human"
        if isinstance(message, AIMessage):
            return "ai"
        if isinstance(message, SystemMessage):
            return "system"
        return "ai"

    @classmethod
    def _get_role_label(cls, message: BaseMessage) -> str:
        """Return a display label for conversation context rendering."""
        return {
            "human": "Human",
            "ai": "AI",
            "system": "System",
        }.get(cls._get_role_key(message), "AI")

    def to_dict(self) -> Dict[str, Any]:
        """
        Export conversation memory to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "messages": [
                {
                    "role": self._get_role_key(msg),
                    "content": msg.content,
                }
                for msg in self.get_messages()
            ],
            "metadata": self.metadata,
            "summary": self.get_summary(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        llm: Optional[ChatOpenAI] = None,
    ) -> "ConversationMemory":
        """
        Create ConversationMemory from dictionary.

        Args:
            data: Dictionary representation
            llm: LLM instance for summarization (required if summary exists)

        Returns:
            ConversationMemory instance

        Raises:
            ValueError: If LLM is not provided but summary exists
        """
        has_summary = data.get("summary") is not None

        # FIXED: Require LLM if summary exists
        if has_summary and llm is None:
            raise ValueError(
                "LLM instance is required when restoring ConversationMemory "
                "with summary. Provide llm parameter to from_dict()."
            )

        memory = cls(
            user_id=data["user_id"],
            session_id=data["session_id"],
            use_summary=has_summary,
            llm=llm,
        )

        # FIXED: Restore summary first (before messages)
        if has_summary and isinstance(memory.memory, ConversationSummaryMemory):
            memory.memory.buffer = data["summary"]
            logger.debug(f"Restored summary for session {memory.session_id}")

        # Restore messages
        for msg_data in data.get("messages", []):
            role = msg_data.get("role", "ai")
            if role == "human":
                memory.add_user_message(msg_data["content"])
            elif role == "ai":
                memory.add_ai_message(msg_data["content"])
            elif role == "system":
                memory.add_system_message(msg_data["content"])
            else:
                raise ValueError(
                    f"unsupported message role '{role}' while restoring memory"
                )

        # Restore metadata
        if "metadata" in data:
            memory.metadata.update(data["metadata"])

        return memory


__all__ = ["ConversationMemory"]
