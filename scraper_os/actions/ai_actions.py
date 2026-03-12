"""
actions/ai_actions.py — AI-powered commands (OmniClick, JinaExtract).

Complex actions that leverage LLMs and VLMs.
"""

import logging
from typing import Any, Dict
from playwright.async_api import Page
from scraper_os.actions.base import BaseAction
from scraper_os.domain.models.dsl import ActionResult, LLMDecision
from scraper_os.domain.registry import register

logger = logging.getLogger(__name__)


@register("omni_click")
class OmniClickAction(BaseAction):
    """Find an element using Omni-Parser and click it."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        target = params.get("target")
        if not target:
            return ActionResult.fail("omni_click", "Missing 'target' parameter.")
        if not llm_facade:
            return ActionResult.fail("omni_click", "LLM Facade not available.")

        try:
            # 1. Take screenshot
            b64 = await self._safe_screenshot(page)
            if not b64:
                return ActionResult.fail("omni_click", "Failed to capture screenshot.")

            # 2. Get coordinates from Omni-Parser
            coords = await llm_facade.get_omni_coordinates(b64, target)
            if "error" in coords:
                return ActionResult.fail(
                    "omni_click", f"Omni-Parser error: {coords['error']}"
                )

            x, y = coords.get("x"), coords.get("y")
            if x is None or y is None:
                return ActionResult.fail(
                    "omni_click", f"Target '{target}' not found by Omni-Parser."
                )

            # 3. Click
            await page.mouse.click(x, y)

            # 4. Return result with optional updated screenshot
            new_b64 = await self._safe_screenshot(page)
            return ActionResult.ok(
                "omni_click", data={"coords": coords}, screenshot=new_b64
            )

        except Exception as exc:
            logger.exception("OmniClick failed")
            return ActionResult.fail("omni_click", str(exc))


@register("jina_extract")
class JinaExtractAction(BaseAction):
    """Extract structured data or Markdown from the page using Jina."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        schema = params.get("schema")
        if not llm_facade:
            return ActionResult.fail("jina_extract", "LLM Facade not available.")

        try:
            html = await page.content()
            result = await llm_facade.get_jina_markdown(html, schema)

            if "error" in result:
                return ActionResult.fail("jina_extract", result["error"])

            return ActionResult.ok("jina_extract", data=result)
        except Exception as exc:
            return ActionResult.fail("jina_extract", str(exc))


@register("smart_step")
class SmartStepAction(BaseAction):
    """Ask LLM to decide the next step and return it as a command recommendation."""

    async def execute(
        self, page: Page, params: Dict[str, Any], llm_facade: Any = None
    ) -> ActionResult:
        objective = params.get("objective")
        if not objective:
            return ActionResult.fail("smart_step", "Missing 'objective' parameter.")
        if not llm_facade:
            return ActionResult.fail("smart_step", "LLM Facade not available.")

        try:
            # 1. Get simplified DOM or screenshot
            # For now, we use a truncated DOM as in the facade
            html = await page.content()

            # 2. Ask LLM
            decision: LLMDecision = await llm_facade.decide_next_action(
                dom_tree=html, objective=objective, response_model=LLMDecision
            )

            if not decision:
                return ActionResult.fail(
                    "smart_step", "LLM failed to provide a decision."
                )

            return ActionResult.ok(
                "smart_step",
                data={
                    "recommended_action": decision.action,
                    "params": decision.params,
                    "reasoning": decision.reasoning,
                },
            )
        except Exception as exc:
            logger.exception("SmartStep failed")
            return ActionResult.fail("smart_step", str(exc))
