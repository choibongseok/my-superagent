"""Google Docs Agent for document generation."""

from typing import Any, Dict, List

from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent


class DocsAgent(BaseAgent):
    """
    Agent for Google Docs generation.

    TODO: Implement in Phase 1
    """

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "docs",
            "version": "0.1",
            "status": "stub",
        }

    def _create_tools(self) -> List[Tool]:
        # TODO: Implement Google Docs API tools
        return []

    def _create_prompt(self) -> ChatPromptTemplate:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a document generation agent. (TODO: Implement)"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["DocsAgent"]
