"""Docs Agent for Google Docs generation."""

import logging
from typing import Any, Dict, Optional

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from google.oauth2.credentials import Credentials

from app.agents.base import BaseAgent
from app.agents.research_agent import ResearchAgent
from app.tools.google_apis import create_google_docs_tool
from app.services.citation.tracker import CitationTracker

logger = logging.getLogger(__name__)


class DocsAgent(BaseAgent):
    """
    Docs Agent for creating Google Docs documents.
    
    Features:
        - Integrated research capability
        - Automatic Google Docs creation
        - Citation management
        - Structured document generation
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        google_credentials: Credentials,
        llm_provider: str = "openai",
        model_name: Optional[str] = None,
        enable_research: bool = True,
        **kwargs
    ):
        """
        Initialize Docs Agent.
        
        Args:
            user_id: User ID
            session_id: Session ID
            google_credentials: Google OAuth2 credentials
            llm_provider: LLM provider
            model_name: Model name
            enable_research: Enable research capability
            **kwargs: Additional arguments for BaseAgent
        """
        super().__init__(
            user_id=user_id,
            session_id=session_id,
            llm_provider=llm_provider,
            model_name=model_name,
            **kwargs
        )
        
        self.google_credentials = google_credentials
        self.enable_research = enable_research
        self.citation_tracker = CitationTracker()
        
        # Initialize research agent if enabled
        self.research_agent = None
        if enable_research:
            self.research_agent = ResearchAgent(
                user_id=user_id,
                session_id=f"{session_id}_research",
                llm_provider=llm_provider,
                model_name=model_name,
            )
        
        # Create tools
        self.tools = [
            create_google_docs_tool(google_credentials)
        ]
        
        # Create agent executor
        self.agent_executor = self._create_agent_executor()
        
        logger.info(f"DocsAgent initialized for session {session_id}")
    
    def _create_agent_executor(self) -> AgentExecutor:
        """Create agent executor with tools and memory."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a document creation assistant specialized in generating well-structured Google Docs. "
                "Your task is to:\n"
                "1. Understand the user's document requirements\n"
                "2. Create comprehensive, well-formatted content\n"
                "3. Use the create_google_doc tool to generate the document\n"
                "4. Include proper citations if research was performed\n\n"
                "Always create professional, well-organized documents."
            )),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )
        
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory.buffer,
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=5,
        )
    
    def create_document(
        self,
        prompt: str,
        title: Optional[str] = None,
        include_research: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a Google Docs document.
        
        Args:
            prompt: Document creation prompt
            title: Document title (auto-generated if None)
            include_research: Whether to perform research first
            **kwargs: Additional arguments
            
        Returns:
            Document creation result with URL and metadata
        """
        logger.info(f"Creating document: {prompt[:100]}...")
        
        # Add user message to memory
        self.add_user_message(prompt)
        
        try:
            # Perform research if requested
            research_context = ""
            sources = []
            
            if include_research and self.research_agent:
                logger.info("Performing research...")
                research_result = self.research_agent.research(prompt)
                research_context = research_result.get("output", "")
                sources = research_result.get("sources", [])
                
                # Merge citation trackers
                if hasattr(self.research_agent, "citation_tracker"):
                    self.citation_tracker = self.research_agent.citation_tracker
            
            # Generate title if not provided
            if not title:
                title = self._generate_title(prompt)
            
            # Create document content
            content = self._generate_content(prompt, research_context, sources)
            
            # Use agent to create document
            agent_input = f"title: {title}, content: {content}"
            result = self.agent_executor.invoke({
                "input": agent_input,
                "chat_history": self.memory.get_messages(),
            })
            
            output = result.get("output", "")
            
            # Extract document URL from output
            doc_url = self._extract_url(output)
            
            # Add AI response to memory
            self.add_ai_message(output)
            
            return {
                "output": output,
                "document_url": doc_url,
                "title": title,
                "sources": sources,
                "citations": self.citation_tracker.get_bibliography(),
            }
            
        except Exception as e:
            logger.error(f"Document creation failed: {e}", exc_info=True)
            error_msg = f"Document creation failed: {str(e)}"
            self.add_ai_message(error_msg)
            return {
                "output": error_msg,
                "error": str(e),
            }
    
    def _generate_title(self, prompt: str) -> str:
        """Generate document title from prompt."""
        # Simple title generation (can be enhanced with LLM)
        words = prompt.split()[:8]
        title = " ".join(words)
        if len(prompt.split()) > 8:
            title += "..."
        return title
    
    def _generate_content(
        self,
        prompt: str,
        research_context: str,
        sources: list
    ) -> str:
        """
        Generate document content.
        
        Args:
            prompt: Original prompt
            research_context: Research results
            sources: Source list
            
        Returns:
            Formatted document content
        """
        # Use LLM to generate structured content
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional document writer. "
                    "Create a well-structured, comprehensive document based on the user's request. "
                    "Include proper sections, headings, and formatting. "
                    "If research is provided, integrate it naturally into the document."
                )
            },
            {
                "role": "user",
                "content": (
                    f"User request: {prompt}\n\n"
                    f"Research context:\n{research_context}\n\n"
                    f"Create a comprehensive document incorporating this information."
                )
            }
        ]
        
        response = self.llm.invoke(messages)
        content = response.content
        
        # Add citations if sources exist
        if sources:
            content += "\n\n## References\n\n"
            for citation in self.citation_tracker.get_bibliography():
                content += f"- {citation}\n"
        
        return content
    
    def _extract_url(self, text: str) -> Optional[str]:
        """Extract document URL from text."""
        import re
        pattern = r'https://docs\.google\.com/document/d/[\w-]+/edit'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    
    def run(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Run docs agent."""
        return self.create_document(prompt, **kwargs)


__all__ = ["DocsAgent"]
