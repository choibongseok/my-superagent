"""Mock LLM provider for DEMO_MODE — Idea #245.

Provides a fake ChatModel that returns realistic-looking responses
without requiring any API keys. Enables instant onboarding and
try-before-you-buy experience.

Usage:
    from app.core.mock_llm import DemoLLM
    llm = DemoLLM()
    result = llm.invoke("Summarize this report")
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from typing import Any, Iterator, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canned response templates by detected intent
# ---------------------------------------------------------------------------

_RESPONSE_TEMPLATES: dict[str, list[str]] = {
    "research": [
        (
            "## Research Summary\n\n"
            "Based on analysis of multiple sources, here are the key findings:\n\n"
            "### Key Insights\n"
            "1. **Market Growth**: The sector shows 15-20% year-over-year growth, "
            "driven by increased adoption of AI and automation technologies.\n"
            "2. **Competitive Landscape**: Three major players dominate with 65% "
            "combined market share, but emerging startups are gaining traction.\n"
            "3. **Trends**: Cloud-native solutions, sustainability initiatives, "
            "and personalization are the top three trends for 2026.\n\n"
            "### Recommendations\n"
            "- Focus on differentiation through AI-powered features\n"
            "- Target mid-market segments with competitive pricing\n"
            "- Invest in developer ecosystem and API partnerships\n\n"
            "*Note: This is a demo response. Connect your API keys for real AI-powered research.*"
        ),
    ],
    "docs": [
        (
            "# Report Draft\n\n"
            "## Executive Summary\n"
            "This report analyzes the current state and provides strategic "
            "recommendations for the upcoming quarter.\n\n"
            "## Key Metrics\n"
            "| Metric | Current | Target | Status |\n"
            "|--------|---------|--------|--------|\n"
            "| Revenue | $125K | $150K | 🟡 On Track |\n"
            "| Users | 1,200 | 1,500 | 🟢 Ahead |\n"
            "| NPS | 42 | 50 | 🟡 On Track |\n\n"
            "## Action Items\n"
            "1. Launch marketing campaign by end of month\n"
            "2. Complete feature X for enterprise clients\n"
            "3. Schedule quarterly review with stakeholders\n\n"
            "*Note: This is a demo response. Connect your API keys for real document generation.*"
        ),
    ],
    "sheets": [
        (
            "## Spreadsheet Analysis\n\n"
            "I've analyzed the data and here's a summary:\n\n"
            "- **Total Records**: 1,247 entries processed\n"
            "- **Average Value**: $3,842.50\n"
            "- **Trend**: Upward (+12.3% MoM)\n"
            "- **Outliers**: 3 entries flagged for review\n\n"
            "### Recommended Charts\n"
            "1. Bar chart: Monthly comparison\n"
            "2. Line chart: Growth trend over 12 months\n"
            "3. Pie chart: Category distribution\n\n"
            "*Note: This is a demo response. Connect your API keys for real spreadsheet analysis.*"
        ),
    ],
    "slides": [
        (
            "## Presentation Outline\n\n"
            "### Slide 1: Title\n"
            "**[Project Name] — Quarterly Review**\n\n"
            "### Slide 2: Highlights\n"
            "- Revenue up 18%\n"
            "- 3 new enterprise clients\n"
            "- Product NPS improved to 45\n\n"
            "### Slide 3: Challenges\n"
            "- Engineering capacity constraints\n"
            "- Competitive pressure in pricing\n\n"
            "### Slide 4: Next Quarter Plan\n"
            "- Launch v2.0 features\n"
            "- Expand to APAC market\n"
            "- Hire 5 engineers\n\n"
            "*Note: This is a demo response. Connect your API keys for real presentation generation.*"
        ),
    ],
    "default": [
        (
            "I've processed your request. Here's what I found:\n\n"
            "Based on the information available, I can provide the following analysis:\n\n"
            "1. **Overview**: The topic covers several interconnected areas that "
            "require careful consideration.\n"
            "2. **Analysis**: Key factors include market dynamics, technical "
            "feasibility, and resource allocation.\n"
            "3. **Recommendation**: A phased approach would minimize risk while "
            "maximizing learning opportunities.\n\n"
            "Would you like me to dive deeper into any specific aspect?\n\n"
            "*Note: This is a demo response. Connect your API keys for full AI capabilities.*"
        ),
    ],
}

# Intent keywords for classification
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "research": ["research", "analyze", "investigate", "study", "find", "search", "trend"],
    "docs": ["report", "document", "write", "draft", "memo", "summary", "article"],
    "sheets": ["spreadsheet", "data", "chart", "excel", "csv", "calculate", "numbers"],
    "slides": ["presentation", "slides", "deck", "pitch", "keynote", "powerpoint"],
}


def _detect_intent(text: str) -> str:
    """Detect the intent from user input to pick an appropriate response."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        scores[intent] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "default"


class DemoLLM(BaseChatModel):
    """A mock ChatModel that returns canned demo responses.

    Looks up intent from the last user message and returns a
    realistic-looking template response with a small artificial delay
    to simulate network latency.
    """

    model_name: str = "demo-mock-v1"
    demo_delay_ms: int = 300

    @property
    def _llm_type(self) -> str:
        return "demo-mock"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Simulate small latency
        time.sleep(self.demo_delay_ms / 1000.0)

        # Extract last human message
        user_text = ""
        for msg in reversed(messages):
            if msg.type == "human":
                user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        intent = _detect_intent(user_text)
        templates = _RESPONSE_TEMPLATES.get(intent, _RESPONSE_TEMPLATES["default"])

        # Use hash for determinism on same input, but still pick from templates
        idx = int(hashlib.md5(user_text.encode()).hexdigest(), 16) % len(templates)
        response_text = templates[idx]

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "demo_delay_ms": self.demo_delay_ms}
