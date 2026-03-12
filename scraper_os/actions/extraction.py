"""
actions/extraction.py — Extraction commands (HTML, Screenshot).

Actions for getting content out of the page.
"""

import logging
from typing import Any, Dict
from playwright.async_api import Page
from scraper_os.actions.base import BaseAction
from scraper_os.domain.models.dsl import ActionResult
from scraper_os.domain.registry import register

logger = logging.getLogger(__name__)


@register("get_html")
class GetHTMLAction(BaseAction):
    """Return the current page HTML."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        selector = params.get("selector")
        try:
            if selector:
                element = await page.query_selector(selector)
                if not element:
                    return ActionResult.fail(
                        "get_html", f"Element not found: {selector}"
                    )
                content = await element.inner_html()
            else:
                content = await page.content()

            return ActionResult.ok("get_html", data={"html": content})
        except Exception as exc:
            return ActionResult.fail("get_html", str(exc))


@register("screenshot")
class ScreenshotAction(BaseAction):
    """Capture a screenshot and return as base64."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        full_page = params.get("full_page", False)
        try:
            b64 = await self._safe_screenshot(page)
            return ActionResult.ok("screenshot", screenshot=b64)
        except Exception as exc:
            return ActionResult.fail("screenshot", str(exc))
