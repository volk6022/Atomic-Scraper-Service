"""
Navigation Actions - действия навигации и взаимодействия со страницей.
"""
import logging
from typing import Dict, Any, Optional
from playwright.async_api import Page

from actions.base import BaseAction
from domain.registry import ActionRegistry

logger = logging.getLogger(__name__)


# === Go To URL ===
@ActionRegistry.register("go_to")
class GoToAction(BaseAction):
    """Перейти на URL"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        url = params.get("url")
        wait_until = params.get("wait_until", "domcontentloaded")
        timeout = params.get("timeout")
        
        if not url:
            return {"success": False, "error": "URL is required"}
        
        try:
            logger.info(f"Going to: {url}")
            
            kwargs = {"wait_until": wait_until}
            if timeout:
                kwargs["timeout"] = timeout
            
            response = await page.goto(url, **kwargs)
            
            return {
                "success": True,
                "data": {
                    "url": page.url,
                    "status": response.status if response else None,
                    "title": await page.title(),
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"GoTo error: {e}")
            return {"success": False, "error": str(e)}


# === Click by Selector ===
@ActionRegistry.register("click")
class ClickAction(BaseAction):
    """Клик по элементу"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        selector = params.get("selector")
        timeout = params.get("timeout", 5000)
        
        if not selector:
            return {"success": False, "error": "Selector is required"}
        
        try:
            logger.info(f"Clicking: {selector}")
            
            await page.click(selector, timeout=timeout)
            
            return {
                "success": True,
                "data": {"clicked": selector},
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Click error: {e}")
            return {"success": False, "error": str(e)}


# === Click by Coordinates ===
@ActionRegistry.register("click_coordinate")
class ClickCoordinateAction(BaseAction):
    """Клик по координатам"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        x = params.get("x")
        y = params.get("y")
        
        if x is None or y is None:
            return {"success": False, "error": "X and Y coordinates are required"}
        
        try:
            logger.info(f"Clicking coordinates: ({x}, {y})")
            
            await page.mouse.click(x, y)
            
            return {
                "success": True,
                "data": {"x": x, "y": y},
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Click coordinate error: {e}")
            return {"success": False, "error": str(e)}


# === Scroll ===
@ActionRegistry.register("scroll")
class ScrollAction(BaseAction):
    """Прокрутка страницы"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        direction = params.get("direction", "down")
        amount = params.get("amount", 300)
        
        try:
            logger.info(f"Scrolling {direction} by {amount}px")
            
            if direction == "down":
                await page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "left":
                await page.evaluate(f"window.scrollBy(-{amount}, 0)")
            elif direction == "right":
                await page.evaluate(f"window.scrollBy({amount}, 0)")
            
            scroll_position = await page.evaluate("""() => ({
                scrollX: window.scrollX,
                scrollY: window.scrollY,
            })""")
            
            return {
                "success": True,
                "data": {
                    "direction": direction,
                    "position": scroll_position,
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Scroll error: {e}")
            return {"success": False, "error": str(e)}


# === Type Text ===
@ActionRegistry.register("type")
class TypeAction(BaseAction):
    """Ввод текста в поле"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        selector = params.get("selector")
        text = params.get("text", "")
        delay = params.get("delay", 0)
        
        if not selector:
            return {"success": False, "error": "Selector is required"}
        
        try:
            logger.info(f"Typing into: {selector}")
            
            await page.fill(selector, text)
            
            if delay > 0:
                await page.type(selector, "", delay=delay)  # Для имитации задержки
            
            return {
                "success": True,
                "data": {"typed": text, "selector": selector},
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Type error: {e}")
            return {"success": False, "error": str(e)}


# === Press Key ===
@ActionRegistry.register("press_key")
class PressKeyAction(BaseAction):
    """Нажатие клавиши"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        key = params.get("key")
        
        if not key:
            return {"success": False, "error": "Key is required"}
        
        try:
            logger.info(f"Pressing key: {key}")
            
            await page.keyboard.press(key)
            
            return {
                "success": True,
                "data": {"pressed": key},
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Press key error: {e}")
            return {"success": False, "error": str(e)}
