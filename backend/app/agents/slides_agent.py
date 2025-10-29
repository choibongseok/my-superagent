"""Google Slides Agent for presentation generation."""

from typing import Any, Dict, List

from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent


class SlidesAgent(BaseAgent):
    """
    Agent for Google Slides generation.

    TODO: Implement in Phase 1
    """

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "slides",
            "version": "0.1",
            "status": "stub",
        }

    def _create_tools(self) -> List[Tool]:
        # TODO: Implement Google Slides API tools
        return []

    def _create_prompt(self) -> ChatPromptTemplate:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a presentation generation agent. (TODO: Implement)"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["SlidesAgent"]
