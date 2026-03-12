"""
actions/navigation.py — Navigation commands (GoTo, Click, Scroll).

Implements basic browser interaction actions.
"""

import logging
from typing import Any, Dict
from playwright.async_api import Page
from scraper_os.actions.base import BaseAction
from scraper_os.domain.models.dsl import ActionResult
from scraper_os.domain.registry import register

logger = logging.getLogger(__name__)


@register("goto")
class GotoAction(BaseAction):
    """Navigate to a specified URL."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        url = params.get("url")
        if not url:
            return ActionResult.fail("goto", "Missing 'url' parameter.")

        timeout = params.get("timeout", 30000)
        wait_until = params.get("wait_until", "networkidle")

        try:
            await page.goto(url, timeout=timeout, wait_until=wait_until)
            return ActionResult.ok("goto", data={"url": page.url})
        except Exception as exc:
            return ActionResult.fail("goto", f"Navigation failed: {exc}")


@register("click")
class ClickAction(BaseAction):
    """Click an element by selector or coordinates."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        selector = params.get("selector")
        x = params.get("x")
        y = params.get("y")

        try:
            if selector:
                await page.click(selector, timeout=params.get("timeout", 10000))
            elif x is not None and y is not None:
                await page.mouse.click(x, y)
            else:
                return ActionResult.fail(
                    "click", "Provide either 'selector' or 'x' and 'y'."
                )

            return ActionResult.ok("click")
        except Exception as exc:
            return ActionResult.fail("click", str(exc))


@register("scroll")
class ScrollAction(BaseAction):
    """Scroll the page."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)

        try:
            if direction == "down":
                await page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")

            return ActionResult.ok("scroll")
        except Exception as exc:
            return ActionResult.fail("scroll", str(exc))
