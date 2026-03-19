from typing import Any, Dict
from playwright.async_api import Page
from src.domain.registry.action_registry import action_registry
from src.domain.models.dsl import CommandType


@action_registry.register(CommandType.CLICK_COORD)
async def click_coord_action(page: Page, params: Dict[str, Any]) -> Dict[str, Any]:
    x = params.get("x")
    y = params.get("y")
    viewport = page.viewport_size
    await page.mouse.click(x * viewport["width"], y * viewport["height"])
    return {"status": "success"}


@action_registry.register(CommandType.TYPE)
async def type_action(page: Page, params: Dict[str, Any]) -> Dict[str, Any]:
    selector = params.get("selector")
    text = params.get("text")
    await page.fill(selector, text)
    return {"status": "success"}
