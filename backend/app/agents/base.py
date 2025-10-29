"""Base agent class with LangChain and LangFuse integration."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.core.langfuse import get_langfuse_handler, trace_llm


class BaseAgent(ABC):
    """
    Base class for all agents with LangChain and LangFuse integration.

    Features:
        - LLM provider abstraction (OpenAI, Anthropic)
        - LangFuse tracing and monitoring
        - Memory management
        - Tool integration
        - Error handling and retry logic
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        llm_provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        memory: Optional[ConversationBufferMemory] = None,
    ):
        """
        Initialize base agent.

        Args:
            user_id: User identifier for tracking
            session_id: Session identifier for grouping
            llm_provider: "openai" or "anthropic"
            model: Model name
            temperature: LLM temperature (0-1)
            max_tokens: Max output tokens
            memory: Optional memory instance
        """
        self.user_id = user_id
        self.session_id = session_id or f"session_{user_id}"

        # LangFuse callback handler (initialize first)
        self.langfuse_handler = get_langfuse_handler(
            user_id=self.user_id,
            session_id=self.session_id,
            metadata=self._get_metadata(),
        )

        # Initialize LLM
        self.llm = self._create_llm(llm_provider, model, temperature, max_tokens)

        # Initialize memory
        self.memory = memory or ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
        )

        # Tools will be set by subclasses
        self.tools: List[Any] = []

        # Agent executor (initialized in subclasses)
        self.agent_executor: Optional[AgentExecutor] = None

    def _create_llm(
        self,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ):
        """Create LLM instance based on provider."""
        if provider == "openai":
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=[self.langfuse_handler] if hasattr(self, 'langfuse_handler') else None,
            )
        elif provider == "anthropic":
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=[self.langfuse_handler] if hasattr(self, 'langfuse_handler') else None,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @abstractmethod
    def _get_metadata(self) -> Dict[str, Any]:
        """Get agent metadata for LangFuse tracking."""
        pass

    @abstractmethod
    def _create_tools(self) -> List[Any]:
        """Create agent-specific tools."""
        pass

    @abstractmethod
    def _create_prompt(self) -> ChatPromptTemplate:
        """Create agent-specific prompt template."""
        pass

    def initialize_agent(self):
        """Initialize agent with tools and prompt."""
        # Create tools
        self.tools = self._create_tools()

        # Create prompt
        prompt = self._create_prompt()

        # Create agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )

        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=settings.DEBUG,
            max_iterations=10,
            max_execution_time=300,  # 5 minutes
            callbacks=[self.langfuse_handler],
        )

    @trace_llm(name="agent_run")
    async def run(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run agent with prompt.

        Args:
            prompt: User prompt
            context: Additional context
            trace_id: LangFuse trace ID (injected by decorator)

        Returns:
            Agent output dictionary
        """
        if not self.agent_executor:
            self.initialize_agent()

        try:
            # Prepare input
            agent_input = {
                "input": prompt,
                **(context or {}),
            }

            # Run agent
            result = await self.agent_executor.ainvoke(
                agent_input,
                config={
                    "callbacks": [self.langfuse_handler],
                    "metadata": {
                        "trace_id": trace_id,
                        "user_id": self.user_id,
                        "session_id": self.session_id,
                    },
                },
            )

            return {
                "output": result.get("output"),
                "intermediate_steps": result.get("intermediate_steps", []),
                "success": True,
            }

        except Exception as e:
            # Log error to LangFuse
            self.langfuse_handler.flush()

            return {
                "output": None,
                "error": str(e),
                "success": False,
            }

    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear()


__all__ = ["BaseAgent"]
