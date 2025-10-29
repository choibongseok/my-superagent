"""Base Agent class for all LangChain agents."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from app.core.config import settings
from app.memory.conversation import ConversationMemory

# LangFuse will be integrated when available
try:
    from langfuse import Langfuse
    from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    LangfuseCallbackHandler = None

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all LangChain agents.
    
    Features:
        - LLM initialization (OpenAI or Anthropic)
        - Memory management (Phase 2 ConversationMemory)
        - LangFuse observability (when available)
        - Abstract methods for agent-specific logic
    
    Fixes:
        - LangFuse handler initialized BEFORE LLM creation (Phase 0 fix)
        - Uses Phase 2 ConversationMemory instead of LangChain's basic memory (Phase 1 fix)
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        llm_provider: str = "openai",
        model_name: Optional[str] = None,
        temperature: float = 0.7,
        enable_langfuse: bool = True,
    ):
        """
        Initialize base agent.
        
        Args:
            user_id: User ID for memory isolation
            session_id: Session ID for conversation tracking
            llm_provider: "openai" or "anthropic"
            model_name: Model name (defaults to provider default)
            temperature: LLM temperature
            enable_langfuse: Enable LangFuse observability
        """
        self.user_id = user_id
        self.session_id = session_id
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.temperature = temperature
        
        # FIXED: Initialize LangFuse handler FIRST (Phase 0 fix)
        self.langfuse_handler = None
        if enable_langfuse and LANGFUSE_AVAILABLE:
            try:
                self.langfuse_handler = self._init_langfuse()
                logger.info(f"LangFuse handler initialized for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize LangFuse: {e}")
        
        # Then create LLM with handler
        self.llm = self._create_llm()
        
        # FIXED: Use Phase 2 ConversationMemory (Phase 1 fix)
        self.memory = self._init_memory()
        
        logger.info(
            f"BaseAgent initialized: provider={llm_provider}, "
            f"model={self.model_name}, session={session_id}"
        )
    
    def _init_langfuse(self) -> Optional[LangfuseCallbackHandler]:
        """
        Initialize LangFuse handler for observability.
        
        Returns:
            LangFuse callback handler or None
        """
        if not LANGFUSE_AVAILABLE:
            return None
        
        try:
            # Initialize LangFuse client
            langfuse = Langfuse(
                public_key=getattr(settings, "LANGFUSE_PUBLIC_KEY", None),
                secret_key=getattr(settings, "LANGFUSE_SECRET_KEY", None),
                host=getattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            
            # Create callback handler
            handler = LangfuseCallbackHandler(
                session_id=self.session_id,
                user_id=self.user_id,
            )
            
            return handler
            
        except Exception as e:
            logger.error(f"Failed to initialize LangFuse: {e}")
            return None
    
    def _create_llm(self):
        """
        Create LLM instance.
        
        Returns:
            LangChain ChatModel instance
        """
        # Prepare callbacks
        callbacks = []
        if self.langfuse_handler:
            callbacks.append(self.langfuse_handler)
        
        # Create LLM based on provider
        if self.llm_provider == "openai":
            model_name = self.model_name or "gpt-4-turbo-preview"
            return ChatOpenAI(
                model=model_name,
                temperature=self.temperature,
                openai_api_key=settings.OPENAI_API_KEY,
                callbacks=callbacks if callbacks else None,
            )
        
        elif self.llm_provider == "anthropic":
            model_name = self.model_name or "claude-3-opus-20240229"
            return ChatAnthropic(
                model=model_name,
                temperature=self.temperature,
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
                callbacks=callbacks if callbacks else None,
            )
        
        else:
            raise ValueError(f"Unknown LLM provider: {self.llm_provider}")
    
    def _init_memory(self) -> ConversationMemory:
        """
        Initialize conversation memory.
        
        FIXED: Use Phase 2 ConversationMemory instead of LangChain's basic memory.
        
        Returns:
            ConversationMemory instance
        """
        return ConversationMemory(
            user_id=self.user_id,
            session_id=self.session_id,
            llm=self.llm,  # Pass LLM for summarization
            max_token_limit=2000,
        )
    
    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Add user message to memory.
        
        Args:
            content: Message content
            metadata: Optional metadata
        """
        self.memory.add_user_message(content, metadata=metadata)
    
    def add_ai_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Add AI message to memory.
        
        Args:
            content: Message content
            metadata: Optional metadata
        """
        self.memory.add_ai_message(content, metadata=metadata)
    
    def get_conversation_history(self) -> List[BaseMessage]:
        """
        Get conversation history.
        
        Returns:
            List of messages
        """
        return self.memory.get_messages()
    
    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear()
    
    @abstractmethod
    def run(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Run agent with given prompt.
        
        Args:
            prompt: User prompt
            **kwargs: Additional arguments
            
        Returns:
            Agent execution result
        """
        pass
    
    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}("
            f"provider={self.llm_provider}, "
            f"session={self.session_id}"
            f")>"
        )
