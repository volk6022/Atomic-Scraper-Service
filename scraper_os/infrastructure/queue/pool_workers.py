"""
Pool Workers - воркеры для Stateless задач (Scraper & Serper).

Используют глобальный BrowserPoolManager, который запускается при старте воркера.
"""
import logging
from typing import Dict, Any, Optional
import asyncio

from infrastructure.queue.broker import broker
from infrastructure.browser.pool_manager import BrowserPoolManager
from core.config import settings

logger = logging.getLogger(__name__)


@broker.on_event("startup")
async def startup_event() -> None:
    """Запустить BrowserPoolManager при старте воркера"""
    await BrowserPoolManager.start()


@broker.on_event("shutdown")
async def shutdown_event() -> None:
    """Закрыть BrowserPoolManager при остановке воркера"""
    await BrowserPoolManager.stop()


@broker.task
async def scrape_task(
    url: str,
    proxy: Optional[str] = None,
    wait_selector: Optional[str] = None,
    wait_timeout: int = 5000,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Задача скрапинга HTML с URL.
    
    Args:
        url: URL для скрапинга
        proxy: Прокси (опционально, переопределяет серверный пул)
        wait_selector: CSS селектор для ожидания (опционально)
        wait_timeout: Таймаут ожидания в мс
        user_agent: User-Agent (опционально)
    
    Returns:
        Dict с результатом:
        {
            "success": bool,
            "data": {"html": str, "url": str, "status": int},
            "error": str или None
        }
    """
    context = None
    
    try:
        logger.info(f"Scraping: {url}")
        
        # Создание контекста
        context = await BrowserPoolManager.new_context(
            proxy=proxy,
            user_agent=user_agent,
        )
        
        page = await context.new_page()
        
        # Переход на URL
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=settings.PLAYWRIGHT_TIMEOUT_SECONDS,
        )
        
        # Ожидание селектора (если указан)
        if wait_selector:
            await page.wait_for_selector(
                wait_selector,
                timeout=wait_timeout,
            )
        
        # Получение HTML
        html = await page.content()
        status = response.status if response else 0
        
        logger.info(f"Scraping completed: {url} (status={status})")
        
        return {
            "success": True,
            "data": {
                "html": html,
                "url": url,
                "status": status,
            },
            "error": None,
        }
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout scraping {url}")
        return {
            "success": False,
            "data": None,
            "error": f"Timeout: exceeded {settings.PLAYWRIGHT_TIMEOUT_SECONDS}ms",
        }
        
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }
        
    finally:
        # Закрытие контекста (браузер остаётся живым)
        if context:
            await context.close()


@broker.task
async def serper_task(
    query: str,
    num_results: int = 10,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Задача поиска через Serper (или аналог).
    
    Args:
        query: Поисковый запрос
        num_results: Количество результатов
        proxy: Прокси (опционально)
    
    Returns:
        Dict с результатом:
        {
            "success": bool,
            "data": {"results": [{"title": str, "url": str, "snippet": str}, ...]},
            "error": str или None
        }
    """
    context = None
    
    try:
        logger.info(f"Serper search: {query}")
        
        # Создание контекста
        context = await BrowserPoolManager.new_context(proxy=proxy)
        
        page = await context.new_page()
        
        # Формирование URL поиска (Google через Serper или прямой поиск)
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={num_results}"
        
        response = await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=settings.PLAYWRIGHT_TIMEOUT_SECONDS,
        )
        
        # Ожидание результатов
        await page.wait_for_selector("#search", timeout=5000)
        
        # Извлечение результатов
        results = await page.evaluate("""() => {
            const items = document.querySelectorAll('.g');
            return Array.from(items).slice(0, 10).map(item => {
                const titleEl = item.querySelector('h3');
                const linkEl = item.querySelector('a');
                const snippetEl = item.querySelector('.VwiC3b');
                return {
                    title: titleEl?.textContent || '',
                    url: linkEl?.href || '',
                    snippet: snippetEl?.textContent || ''
                };
            });
        }""")
        
        logger.info(f"Serper search completed: {len(results)} results")
        
        return {
            "success": True,
            "data": {
                "results": results,
                "query": query,
            },
            "error": None,
        }
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout searching: {query}")
        return {
            "success": False,
            "data": None,
            "error": f"Timeout: exceeded {settings.PLAYWRIGHT_TIMEOUT_SECONDS}ms",
        }
        
    except Exception as e:
        logger.error(f"Error searching {query}: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }
        
    finally:
        if context:
            await context.close()
