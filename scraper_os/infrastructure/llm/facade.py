"""
infrastructure/llm/facade.py — Unified AI Interface (Facade Pattern).

Provides a single point of entry for all AI-related tasks:
extraction, vision analysis, and decision making.
"""

import logging
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel
import httpx

from scraper_os.infrastructure.llm.jina_client import JinaClient
from scraper_os.infrastructure.llm.openai_client import OpenAIClient
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


class LLMFacade:
    """Facade for interacting with multiple LLM/VLM services."""

    def __init__(self):
        self.jina = JinaClient()
        self.openai = OpenAIClient()
        self.omni_url = settings.omni_parser_url

    async def get_jina_markdown(
        self, html: str, extract_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Convert HTML to clean Markdown or extract structured data via Jina."""
        return await self.jina.extract_markdown(html, extract_schema)

    async def get_omni_coordinates(
        self, base64_image: str, target: str
    ) -> Dict[str, Any]:
        """Call Omni-Parser to find coordinates for a target element.

        If Omni-Parser URL is not configured, it falls back to a mock or error.
        """
        if not self.omni_url:
            logger.warning(
                "Omni-Parser URL not configured. Returning mock coordinates."
            )
            # For demonstration, we'll return a mock if not configured.
            return {"x": 100, "y": 100, "confidence": 0.5}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.omni_url, json={"image": base64_image, "target": target}
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                logger.error("Omni-Parser call failed: %s", exc)
                return {"error": str(exc)}

    async def decide_next_action(
        self, dom_tree: str, objective: str, response_model: Type[BaseModel]
    ) -> Any:
        """Ask the LLM to decide the next step based on the current page state."""
        prompt = (
            f"Objective: {objective}\n\n"
            f"Current Page DOM (truncated):\n{dom_tree[:5000]}\n\n"
            "What is the next action to take to achieve the objective?"
        )
        return await self.openai.get_structured_output(prompt, response_model)

    async def analyze_visual_state(self, base64_image: str, question: str) -> str:
        """Answer a question about the page's visual appearance."""
        return await self.openai.analyze_screenshot(base64_image, question)
