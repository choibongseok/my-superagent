"""Base agent class with LangChain and LangFuse integration.

This module provides the foundation for all agents in AgentHQ with proper
integration of LangChain agent framework, LangFuse observability, and Phase 2
memory systems.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.core.llm_fallback import build_llm_with_fallbacks
from app.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

# Check LangFuse availability
LANGFUSE_AVAILABLE = False
try:
    from langfuse.callback import CallbackHandler
    LANGFUSE_AVAILABLE = True
except ImportError:
    logger.warning("LangFuse not available - tracing disabled")


class BaseAgent(ABC):
    """
    Base class for all agents with LangChain and LangFuse integration.

    Features:
        - LLM provider abstraction (OpenAI, Anthropic)
        - LangFuse tracing and monitoring (when available)
        - Phase 2 MemoryManager integration (conversation + vector memory)
        - Tool integration via LangChain
        - Proper initialization order for callbacks
        - Error handling and retry logic

    Critical Implementation Details:
        1. LangFuse handler MUST be initialized BEFORE LLM creation
        2. MemoryManager (Phase 2) provides both short-term and long-term memory
        3. Memory buffer is passed to AgentExecutor for chat_history
        4. Helper methods (add_user_message, add_ai_message) provided

    Usage:
        class MyAgent(BaseAgent):
            def _get_metadata(self):
                return {"agent_type": "custom"}
            
            def _create_tools(self):
                return [MyTool()]
            
            def _create_prompt(self):
                return ChatPromptTemplate.from_messages([...])
        
        agent = MyAgent(user_id="user123", session_id="sess456")
        result = await agent.run("Do something")
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        credentials: Optional[Credentials] = None,
        llm_provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        enable_langfuse: bool = True,
    ):
        """
        Initialize base agent with proper initialization order.

        Args:
            user_id: User identifier for tracking
            session_id: Session identifier for grouping (auto-generated if None)
            credentials: Optional Google OAuth credentials passed from caller
            llm_provider: "openai" or "anthropic"
            model: Model name (e.g., "gpt-4-turbo-preview", "claude-3-opus")
            temperature: LLM temperature (0-1)
            max_tokens: Max output tokens
            enable_langfuse: Enable LangFuse tracing (default: True)

        Note:
            LLM construction is deferred until first access of ``self.llm`` so
            that agent objects can be created and inspected without requiring
            API credentials (e.g., in tests or CLI tooling).
        """
        self.user_id = user_id
        self.session_id = session_id or f"session_{user_id}"
        self.credentials = credentials

        # Store LLM config — actual LLM is created lazily on first access
        self._llm_provider = llm_provider
        self._llm_model = model
        self._llm_temperature = temperature
        self._llm_max_tokens = max_tokens
        self._llm_instance = None  # populated lazily

        # LangFuse handler (also lazy — needs LLM params, not LLM itself)
        self._enable_langfuse = enable_langfuse
        self._langfuse_handler_initialised = False
        self._langfuse_handler: Optional[Any] = None

        # Memory: no API key required — safe to initialise eagerly
        self.memory: MemoryManager = self._init_memory()

        # Tools will be set by subclasses
        self.tools: List[BaseTool] = []

        # Agent executor (initialised in subclasses via initialize_agent)
        self.agent_executor: Optional[AgentExecutor] = None

        logger.info(
            f"BaseAgent initialised: user={user_id}, session={session_id}, "
            f"provider={llm_provider}, model={model}"
        )

    # ── Lazy LangFuse handler ─────────────────────────────────────────────

    @property
    def langfuse_handler(self) -> Optional[Any]:
        """LangFuse callback handler, created on first access."""
        if not self._langfuse_handler_initialised:
            self._langfuse_handler_initialised = True
            if self._enable_langfuse and LANGFUSE_AVAILABLE:
                self._langfuse_handler = self._init_langfuse()
        return self._langfuse_handler

    @langfuse_handler.setter
    def langfuse_handler(self, value: Optional[Any]) -> None:
        """Allow direct assignment (e.g., in tests)."""
        self._langfuse_handler = value
        self._langfuse_handler_initialised = True

    # ── Lazy LLM ─────────────────────────────────────────────────────────

    @property
    def llm(self):
        """LLM instance, created on first access.

        Raises:
            ValueError: if provider is unsupported.
            openai.OpenAIError / anthropic.AuthenticationError: if the
                corresponding API key is missing at call time.
        """
        if self._llm_instance is None:
            self._llm_instance = self._create_llm(
                self._llm_provider,
                self._llm_model,
                self._llm_temperature,
                self._llm_max_tokens,
            )
        return self._llm_instance

    @llm.setter
    def llm(self, value) -> None:
        """Allow direct assignment (e.g., test injection)."""
        self._llm_instance = value

    def _init_langfuse(self) -> Optional[Any]:
        """
        Initialize LangFuse callback handler.

        Returns:
            LangFuse CallbackHandler or None if unavailable
        """
        if not LANGFUSE_AVAILABLE:
            return None

        try:
            from langfuse.callback import CallbackHandler
            
            handler = CallbackHandler(
                user_id=self.user_id,
                session_id=self.session_id,
                metadata=self._get_metadata(),
            )
            
            logger.debug(f"LangFuse handler initialized for session {self.session_id}")
            return handler
        
        except Exception as e:
            logger.warning(f"Failed to initialize LangFuse handler: {e}")
            return None

    def _init_memory(self) -> MemoryManager:
        """
        Initialize Phase 2 MemoryManager with conversation and vector memory.

        Returns:
            MemoryManager instance
        """
        memory = MemoryManager(
            user_id=self.user_id,
            session_id=self.session_id,
            use_vector_memory=True,  # Enable long-term memory
            use_summary=False,  # Can be enabled with LLM parameter
            conversation_max_tokens=2000,
            vector_top_k=5,
            # Do NOT access self.llm here — it would trigger eager LLM
            # creation during __init__, defeating lazy initialisation.
            llm=None,
        )
        
        logger.debug(f"MemoryManager initialized for session {self.session_id}")
        return memory

    def _create_llm(
        self,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        """
        Create LLM instance with automatic multi-model fallback (#232).

        When multiple API keys are configured (e.g. OPENAI_API_KEY and
        ANTHROPIC_API_KEY), the returned LLM will transparently retry on
        the next provider if the primary one fails.

        Args:
            provider: Preferred provider ("openai" or "anthropic")
            model: Preferred model name
            temperature: Temperature (0-1)
            max_tokens: Max output tokens

        Returns:
            LLM instance — a single ChatModel or RunnableWithFallbacks
        """
        callbacks = [self.langfuse_handler] if self.langfuse_handler else None

        return build_llm_with_fallbacks(
            primary_provider=provider,
            primary_model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            callbacks=callbacks,
        )

    @abstractmethod
    def _get_metadata(self) -> Dict[str, Any]:
        """
        Get agent metadata for LangFuse tracking.

        Returns:
            Metadata dictionary with agent info
        """
        pass

    @abstractmethod
    def _create_tools(self) -> List[BaseTool]:
        """
        Create agent-specific tools.

        Returns:
            List of LangChain tools
        """
        pass

    @abstractmethod
    def _create_prompt(self) -> ChatPromptTemplate:
        """
        Create agent-specific prompt template.

        Returns:
            ChatPromptTemplate with system message and placeholders
        """
        pass

    def initialize_agent(self):
        """
        Initialize agent with tools, prompt, and executor.

        This method:
        1. Creates tools via _create_tools()
        2. Creates prompt via _create_prompt()
        3. Creates tool-calling agent
        4. Creates AgentExecutor with memory
        """
        # Create tools
        self.tools = self._create_tools()
        logger.debug(f"Created {len(self.tools)} tools for {self.__class__.__name__}")

        # Create prompt
        prompt = self._create_prompt()

        # Create agent with tool calling
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )

        # FIXED: Create executor with memory.langchain_memory for chat_history
        callbacks = [self.langfuse_handler] if self.langfuse_handler else []
        
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory.langchain_memory,  # Pass langchain_memory for LangChain compatibility
            verbose=settings.DEBUG,
            max_iterations=10,
            max_execution_time=300,  # 5 minutes
            callbacks=callbacks,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

        logger.info(f"{self.__class__.__name__} initialized with {len(self.tools)} tools")

    def _extract_token_usage(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract token usage from LLM response.
        
        Args:
            result: AgentExecutor result dictionary
            
        Returns:
            Token usage dict or None if not available
        """
        try:
            # Try to extract from intermediate steps (tool calls may have usage info)
            intermediate_steps = result.get("intermediate_steps", [])
            
            total_prompt_tokens = 0
            total_completion_tokens = 0
            
            for step in intermediate_steps:
                if isinstance(step, tuple) and len(step) == 2:
                    action, observation = step
                    
                    # Check if observation has usage info (from LLM calls)
                    if hasattr(observation, "response_metadata"):
                        metadata = observation.response_metadata
                        usage = metadata.get("usage", {})
                        
                        total_prompt_tokens += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                        total_completion_tokens += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            
            # Also check the final output for usage info
            if "response_metadata" in result:
                usage = result["response_metadata"].get("usage", {})
                total_prompt_tokens += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            
            if total_prompt_tokens > 0 or total_completion_tokens > 0:
                return {
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                    "model": self._llm_model,
                    "provider": self._llm_provider,
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract token usage: {e}")
            return None

    async def run(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run agent with user prompt.

        Args:
            prompt: User prompt/query
            context: Optional additional context

        Returns:
            Result dictionary with output, intermediate_steps, token_usage, and success flag
        """
        if not self.agent_executor:
            self.initialize_agent()

        try:
            # Add user message to memory
            self.add_user_message(prompt)

            # Prepare input
            agent_input = {
                "input": prompt,
                **(context or {}),
            }

            # Run agent
            callbacks = [self.langfuse_handler] if self.langfuse_handler else []
            
            result = await self.agent_executor.ainvoke(
                agent_input,
                config={
                    "callbacks": callbacks,
                    "metadata": {
                        "user_id": self.user_id,
                        "session_id": self.session_id,
                    },
                },
            )

            # Extract output
            output = result.get("output", "")
            
            # Add AI message to memory
            self.add_ai_message(output)
            
            # Extract token usage
            token_usage = self._extract_token_usage(result)

            return {
                "output": output,
                "intermediate_steps": result.get("intermediate_steps", []),
                "token_usage": token_usage,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            
            # Flush LangFuse traces
            if self.langfuse_handler:
                try:
                    self.langfuse_handler.flush()
                except:
                    pass

            return {
                "output": None,
                "error": str(e),
                "token_usage": None,
                "success": False,
            }

    # Helper methods for memory management

    def add_user_message(self, message: str):
        """
        Add user message to conversation memory.

        Args:
            message: User message content
        """
        self.memory.add_user_message(message)

    def add_ai_message(self, message: str):
        """
        Add AI message to conversation memory.

        Args:
            message: AI message content
        """
        self.memory.add_ai_message(message)

    def get_conversation_history(self) -> str:
        """
        Get formatted conversation history.

        Returns:
            Formatted conversation context
        """
        return self.memory.get_context()

    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear()
        logger.info(f"Memory cleared for session {self.session_id}")


__all__ = ["BaseAgent"]
