"""Base agent class with LangChain and LangFuse integration.

This module provides the foundation for all agents in AgentHQ with proper
integration of LangChain agent framework, LangFuse observability, and Phase 2
memory systems.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.memory.conversation import ConversationMemory

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
        - Phase 2 ConversationMemory integration
        - Tool integration via LangChain
        - Proper initialization order for callbacks
        - Error handling and retry logic

    Critical Implementation Details:
        1. LangFuse handler MUST be initialized BEFORE LLM creation
        2. ConversationMemory (Phase 2) is used instead of basic buffer
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
            llm_provider: "openai" or "anthropic"
            model: Model name (e.g., "gpt-4-turbo-preview", "claude-3-opus")
            temperature: LLM temperature (0-1)
            max_tokens: Max output tokens
            enable_langfuse: Enable LangFuse tracing (default: True)
        """
        self.user_id = user_id
        self.session_id = session_id or f"session_{user_id}"

        # CRITICAL: Initialize LangFuse handler FIRST (before LLM creation)
        self.langfuse_handler = None
        if enable_langfuse and LANGFUSE_AVAILABLE:
            self.langfuse_handler = self._init_langfuse()

        # Then create LLM with the handler
        self.llm = self._create_llm(llm_provider, model, temperature, max_tokens)

        # FIXED: Use Phase 2 ConversationMemory instead of basic buffer
        self.memory = self._init_memory()

        # Tools will be set by subclasses
        self.tools: List[BaseTool] = []

        # Agent executor (initialized in subclasses via initialize_agent)
        self.agent_executor: Optional[AgentExecutor] = None

        logger.info(
            f"BaseAgent initialized: user={user_id}, session={session_id}, "
            f"provider={llm_provider}, model={model}, langfuse={self.langfuse_handler is not None}"
        )

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

    def _init_memory(self) -> ConversationMemory:
        """
        Initialize Phase 2 ConversationMemory.

        Returns:
            ConversationMemory instance
        """
        memory = ConversationMemory(
            user_id=self.user_id,
            session_id=self.session_id,
            max_token_limit=2000,
            use_summary=False,  # Can be enabled with LLM parameter
            llm=self.llm if hasattr(self, 'llm') else None,
        )
        
        logger.debug(f"ConversationMemory initialized for session {self.session_id}")
        return memory

    def _create_llm(
        self,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        """
        Create LLM instance based on provider with LangFuse callbacks.

        Args:
            provider: "openai" or "anthropic"
            model: Model name
            temperature: Temperature (0-1)
            max_tokens: Max output tokens

        Returns:
            LLM instance (ChatOpenAI or ChatAnthropic)
        """
        callbacks = [self.langfuse_handler] if self.langfuse_handler else None

        if provider == "openai":
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=callbacks,
            )
        elif provider == "anthropic":
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=callbacks,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

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

        # FIXED: Create executor with memory.buffer for chat_history
        callbacks = [self.langfuse_handler] if self.langfuse_handler else []
        
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory.buffer,  # Pass buffer for LangChain compatibility
            verbose=settings.DEBUG,
            max_iterations=10,
            max_execution_time=300,  # 5 minutes
            callbacks=callbacks,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

        logger.info(f"{self.__class__.__name__} initialized with {len(self.tools)} tools")

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
            Result dictionary with output, intermediate_steps, and success flag
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

            return {
                "output": output,
                "intermediate_steps": result.get("intermediate_steps", []),
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
