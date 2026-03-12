"""
infrastructure/llm/openai_client.py — OpenAI API Client.

Handles structured output for decision making and interaction with
VLM models for Omni-Parser support.
"""

import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel
import openai
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for OpenAI-compatible APIs."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )

    async def get_structured_output(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        system_prompt: str = "You are a helpful web automation assistant.",
        model: Optional[str] = None,
    ) -> Any:
        """Call OpenAI with a Pydantic model for structured output."""
        target_model = model or settings.openai_model
        try:
            completion = await self.client.beta.chat.completions.parse(  # type: ignore
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format=response_model,
            )
            return completion.choices[0].message.parsed
        except Exception as exc:
            logger.error("OpenAI structured output failed: %s", exc)
            return None

    async def analyze_screenshot(
        self, base64_image: str, prompt: str, model: Optional[str] = None
    ) -> str:
        """Analyze a screenshot using a Vision-capable model."""
        target_model = model or settings.openai_model
        try:
            response = await self.client.chat.completions.create(
                model=target_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
            )
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as exc:
            logger.error("OpenAI vision analysis failed: %s", exc)
            return f"Error: {exc}"
