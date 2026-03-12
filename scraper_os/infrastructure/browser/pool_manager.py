"""
Browser Pool Manager - глобальный инстанс Playwright для Stateless задач.

Паттерн: Синглтон.
Жизненный цикл: Запускается при старте воркера, закрывается при остановке.
"""
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from core.config import settings

logger = logging.getLogger(__name__)


class BrowserPoolManager:
    """
    Менеджер пула браузеров для Stateless задач (Scraper/Serper).
    
    Использование:
        1. При старте воркера: await BrowserPoolManager.start()
        2. Для задач: context = await BrowserPoolManager.new_context(proxy)
        3. При остановке воркера: await BrowserPoolManager.stop()
    """
    
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _proxy_index: int = 0
    
    @classmethod
    async def start(cls) -> None:
        """
        Запустить Playwright и браузер.
        Вызывается при старте воркера (@broker.on_event('startup')).
        """
        if cls._browser is not None:
            logger.warning("Browser already started")
            return
        
        logger.info("Starting BrowserPoolManager...")
        
        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch(
            headless=settings.HEADLESS_DEFAULT,
            channel=settings.CHROMIUM_CHANNEL if settings.CHROMIUM_CHANNEL != "chromium" else None,
        )
        
        logger.info("BrowserPoolManager started successfully")
    
    @classmethod
    async def stop(cls) -> None:
        """
        Закрыть браузер и Playwright.
        Вызывается при остановке воркера (@broker.on_event('shutdown')).
        """
        logger.info("Stopping BrowserPoolManager...")
        
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None
        
        logger.info("BrowserPoolManager stopped")
    
    @classmethod
    async def new_context(
        cls,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
    ) -> BrowserContext:
        """
        Создать новый изолированный контекст для задачи.
        
        Args:
            proxy: Прокси сервер (например, "http://user:pass@host:port")
            user_agent: User-Agent строка
            viewport_width: Ширина вьюпорта
            viewport_height: Высота вьюпорта
        
        Returns:
            BrowserContext для выполнения задачи
        """
        if cls._browser is None:
            raise RuntimeError("BrowserPoolManager not started. Call start() first.")
        
        # Формирование настроек прокси
        proxy_settings = None
        if proxy:
            proxy_settings = {"server": proxy}
        elif settings.has_server_proxies:
            # Round-robin выборка из серверного пула
            proxy, cls._proxy_index = settings.get_next_proxy("scraper", cls._proxy_index)
            if proxy:
                proxy_settings = {"server": proxy}
                logger.debug(f"Using proxy from pool: {proxy[:20]}...")
        
        # Настройки контекста
        context_options = {
            "proxy": proxy_settings,
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
        
        if user_agent:
            context_options["user_agent"] = user_agent
        
        context = await cls._browser.new_context(**context_options)
        logger.debug(f"Created new browser context")
        
        return context
    
    @classmethod
    def is_running(cls) -> bool:
        """Проверить, запущен ли браузер"""
        return cls._browser is not None
