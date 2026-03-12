"""
Extraction Actions - действия извлечения данных со страницы.
"""
import base64
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page

from actions.base import BaseAction
from domain.registry import ActionRegistry

logger = logging.getLogger(__name__)


# === Screenshot ===
@ActionRegistry.register("screenshot")
class ScreenshotAction(BaseAction):
    """Сделать скриншот страницы"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        full_page = params.get("full_page", False)
        quality = params.get("quality", 80)
        
        try:
            logger.info(f"Taking screenshot (full_page={full_page})")
            
            # Скриншот в base64
            screenshot = await page.screenshot(
                full_page=full_page,
                quality=quality,
                type="jpeg",
            )
            
            # Конвертация в base64
            base64_image = base64.b64encode(screenshot).decode("utf-8")
            
            return {
                "success": True,
                "data": {
                    "image": base64_image,
                    "format": "base64",
                    "full_page": full_page,
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {"success": False, "error": str(e)}


# === Extract HTML ===
@ActionRegistry.register("extract_html")
class ExtractHTMLAction(BaseAction):
    """Извлечь HTML страницы или элемента"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        selector = params.get("selector")
        
        try:
            if selector:
                # Извлечь HTML конкретного элемента
                element = await page.query_selector(selector)
                if element:
                    html = await element.inner_html()
                else:
                    return {
                        "success": False,
                        "error": f"Element not found: {selector}",
                    }
            else:
                # Извлечь весь HTML страницы
                html = await page.content()
            
            return {
                "success": True,
                "data": {
                    "html": html,
                    "url": page.url,
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Extract HTML error: {e}")
            return {"success": False, "error": str(e)}


# === Extract Text ===
@ActionRegistry.register("extract_text")
class ExtractTextAction(BaseAction):
    """Извлечь текст страницы или элемента"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        selector = params.get("selector")
        
        try:
            if selector:
                # Извлечь текст конкретного элемента
                text = await page.inner_text(selector)
            else:
                # Извлечь весь текст страницы
                text = await page.inner_text("body")
            
            return {
                "success": True,
                "data": {
                    "text": text,
                    "url": page.url,
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Extract text error: {e}")
            return {"success": False, "error": str(e)}


# === Extract Markdown (через Jina) ===
@ActionRegistry.register("extract_markdown")
class ExtractMarkdownAction(BaseAction):
    """Извлечь Markdown через Jina Reader"""
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if llm_facade is None:
            return {
                "success": False,
                "error": "LLMFacade is required for extract_markdown",
            }
        
        try:
            logger.info("Extracting markdown via Jina")
            
            # Получаем HTML страницы
            html = await page.content()
            url = page.url
            
            # Конвертируем через Jina
            result = await llm_facade.get_jina_markdown(html=html)
            
            if result["success"]:
                return {
                    "success": True,
                    "data": {
                        "markdown": result["data"]["markdown"],
                        "url": url,
                    },
                    "error": None,
                }
            else:
                return result
            
        except Exception as e:
            logger.error(f"Extract markdown error: {e}")
            return {"success": False, "error": str(e)}


# === Omni Click (AI + Click) ===
@ActionRegistry.register("omni_click")
class OmniClickAction(BaseAction):
    """
    Найти элемент на скриншоте через AI и кликнуть по нему.
    
    Комбинирует:
    1. Скриншот страницы
    2. Omni-Parser для поиска координат
    3. Клик по координатам
    """
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        target = params.get("target")
        
        if not target:
            return {"success": False, "error": "Target description is required"}
        
        if llm_facade is None:
            return {
                "success": False,
                "error": "LLMFacade is required for omni_click",
            }
        
        try:
            logger.info(f"Omni click: {target}")
            
            # 1. Скриншот
            screenshot = await page.screenshot(type="png")
            base64_image = base64.b64encode(screenshot).decode("utf-8")
            
            # 2. Поиск координат через AI
            coords_result = await llm_facade.get_omni_coordinates(
                base64_image,
                target,
            )
            
            if not coords_result["success"]:
                return coords_result
            
            x = coords_result["data"]["x"]
            y = coords_result["data"]["y"]
            
            # 3. Клик по координатам
            await page.mouse.click(x, y)
            
            return {
                "success": True,
                "data": {
                    "clicked": target,
                    "x": x,
                    "y": y,
                    "confidence": coords_result["data"].get("confidence"),
                },
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"Omni click error: {e}")
            return {"success": False, "error": str(e)}


# === AI Decision Action ===
@ActionRegistry.register("ai_decide")
class AIDecideAction(BaseAction):
    """
    Принять решение о следующем действии через AI.
    
    Анализирует DOM и цель, возвращает рекомендуемое действие.
    """
    
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None,
    ) -> Dict[str, Any]:
        objective = params.get("objective")
        
        if not objective:
            return {"success": False, "error": "Objective is required"}
        
        if llm_facade is None:
            return {
                "success": False,
                "error": "LLMFacade is required for ai_decide",
            }
        
        try:
            logger.info(f"AI deciding for objective: {objective}")
            
            # Получаем упрощённое DOM дерево
            dom_tree = await page.evaluate("""() => {
                function simplifyNode(node, depth = 0) {
                    if (depth > 3) return null;
                    if (node.nodeType !== 1) return null;
                    
                    const tag = node.tagName.toLowerCase();
                    const id = node.id ? '#' + node.id : '';
                    const classes = node.className ? '.' + node.className.split(' ').join('.') : '';
                    const text = (node.textContent || '').trim().substring(0, 50);
                    
                    return {
                        tag: tag + id + classes,
                        text: text,
                        children: Array.from(node.children)
                            .map(child => simplifyNode(child, depth + 1))
                            .filter(Boolean)
                    };
                }
                return JSON.stringify(simplifyNode(document.body));
            }""")
            
            # AI решение
            decision = await llm_facade.decide_next_action(dom_tree, objective)
            
            return {
                "success": True,
                "data": decision,
                "error": None,
            }
            
        except Exception as e:
            logger.error(f"AI decide error: {e}")
            return {"success": False, "error": str(e)}
