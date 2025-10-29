"""Research Agent for web research and information gathering."""

import logging
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.base import BaseAgent
from app.tools.web_search import create_web_search_tool
from app.services.citation.tracker import CitationTracker
from app.services.citation.models import SourceType

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Research Agent for comprehensive web research.
    
    Features:
        - Web search using DuckDuckGo
        - Source citation tracking
        - Multi-turn conversation support
        - Structured research output
    
    Fixes:
        - Uses Phase 2 ConversationMemory (inherited from BaseAgent)
        - Memory properly passed to AgentExecutor (Phase 1 fix)
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        llm_provider: str = "openai",
        model_name: Optional[str] = None,
        max_search_results: int = 5,
        **kwargs
    ):
        """
        Initialize Research Agent.
        
        Args:
            user_id: User ID
            session_id: Session ID
            llm_provider: LLM provider ("openai" or "anthropic")
            model_name: Model name
            max_search_results: Maximum search results per query
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            user_id=user_id,
            session_id=session_id,
            llm_provider=llm_provider,
            model_name=model_name,
            **kwargs
        )
        
        self.max_search_results = max_search_results
        self.citation_tracker = CitationTracker()
        
        # Create tools
        self.tools = [
            create_web_search_tool(max_results=max_search_results)
        ]
        
        # Create agent executor
        self.agent_executor = self._create_agent_executor()
        
        logger.info(f"ResearchAgent initialized for session {session_id}")
    
    def _create_agent_executor(self) -> AgentExecutor:
        """
        Create agent executor with tools and memory.
        
        FIXED: Pass memory to AgentExecutor (Phase 1 fix)
        
        Returns:
            AgentExecutor instance
        """
        # Create prompt with memory placeholder
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a research assistant specialized in finding and analyzing information from the web. "
                "Your task is to:\n"
                "1. Search for relevant information using the web_search tool\n"
                "2. Analyze and synthesize the information\n"
                "3. Provide well-structured answers with proper citations\n"
                "4. Track sources for citation purposes\n\n"
                "Always cite your sources and provide comprehensive answers."
            )),
            # FIXED: Memory placeholder for multi-turn conversations
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        # Create OpenAI functions agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )
        
        # FIXED: Create executor WITH memory (Phase 1 fix)
        executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory.buffer,  # Pass ConversationMemory's buffer
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=5,
        )
        
        return executor
    
    def research(
        self,
        query: str,
        track_citations: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform research on a query.
        
        Args:
            query: Research query
            track_citations: Whether to track citations
            **kwargs: Additional arguments
            
        Returns:
            Research results with output, sources, and citations
        """
        logger.info(f"Starting research: {query[:100]}...")
        
        # Add user message to memory
        self.add_user_message(query)
        
        try:
            # Run agent with memory context
            result = self.agent_executor.invoke({
                "input": query,
                "chat_history": self.memory.get_messages(),  # Pass conversation history
            })
            
            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Add AI response to memory
            self.add_ai_message(output)
            
            # Extract and track citations if enabled
            sources = []
            if track_citations:
                sources = self._extract_sources(intermediate_steps)
                for source in sources:
                    self.citation_tracker.add_source(**source)
            
            return {
                "output": output,
                "sources": sources,
                "intermediate_steps": intermediate_steps,
                "citations": self.citation_tracker.get_bibliography() if track_citations else [],
            }
            
        except Exception as e:
            logger.error(f"Research failed: {e}", exc_info=True)
            error_msg = f"Research failed: {str(e)}"
            self.add_ai_message(error_msg)
            return {
                "output": error_msg,
                "sources": [],
                "error": str(e),
            }
    
    def _extract_sources(self, intermediate_steps: List) -> List[Dict[str, Any]]:
        """
        Extract sources from intermediate steps.
        
        Args:
            intermediate_steps: Agent intermediate steps
            
        Returns:
            List of source dictionaries
        """
        sources = []
        
        for action, observation in intermediate_steps:
            if action.tool == "web_search":
                # Parse search results
                lines = observation.split("\n")
                current_source = {}
                
                for line in lines:
                    line = line.strip()
                    if line.startswith("URL:"):
                        url = line.replace("URL:", "").strip()
                        current_source["url"] = url
                    elif line and not line[0].isdigit() and current_source.get("url"):
                        # This is likely a title
                        current_source["title"] = line
                        current_source["type"] = SourceType.WEB
                        sources.append(current_source.copy())
                        current_source = {}
        
        return sources
    
    def run(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Run research agent.
        
        Args:
            prompt: Research prompt
            **kwargs: Additional arguments
            
        Returns:
            Research results
        """
        return self.research(prompt, **kwargs)
    
    def get_citations(self, style: str = "apa") -> List[str]:
        """
        Get formatted citations.
        
        Args:
            style: Citation style ("apa", "mla", or "chicago")
            
        Returns:
            List of formatted citations
        """
        return self.citation_tracker.get_bibliography(style=style)


__all__ = ["ResearchAgent"]
