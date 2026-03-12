"""
infrastructure/llm/jina_client.py — Jina Reader V2 Client.

Uses HTTPX to call the Jina Reader V2 HuggingFace Endpoint for
Markdown extraction and structured data parsing.
"""

import logging
from typing import Any, Dict, Optional
import httpx
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


class JinaClient:
    """Client for Jina Reader V2 API."""

    def __init__(self):
        self.api_url = settings.jina_api_url or "https://r.jina.ai/"
        self.api_key = settings.jina_api_key

    async def extract_markdown(
        self, url_or_html: str, extract_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Convert HTML to Markdown or extract structured data.

        If url_or_html starts with http, it treats it as a URL.
        Otherwise, it treats it as raw HTML.
        """
        if not self.api_url:
            return {"error": "Jina API URL not configured."}

        headers = {
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if settings.jina_model:
            headers["X-Model"] = settings.jina_model

        if extract_schema:
            headers["X-Return-Format"] = "json"
            headers["X-Schema"] = str(extract_schema)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Jina Reader expects the URL as part of the path or HTML in the body
                if url_or_html.startswith("http"):
                    target_url = f"{self.api_url.rstrip('/')}/{url_or_html}"
                    response = await client.get(target_url, headers=headers)
                else:
                    response = await client.post(
                        self.api_url, headers=headers, content=url_or_html
                    )

                response.raise_for_status()
                return response.json()
            except Exception as exc:
                logger.error("Jina extraction failed: %s", exc)
                return {"error": str(exc)}
