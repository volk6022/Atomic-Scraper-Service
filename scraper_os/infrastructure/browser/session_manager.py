"""
Session Browser Manager - изолированный браузер для Stateful сессий.

Каждая сессия создаёт свой собственный экземпляр Playwright и браузера.
Жизненный цикл управляется через таймаут бездействия.
"""
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from domain.models import SessionConfig
from core.config import settings

logger = logging.getLogger(__name__)


class SessionBrowserManager:
    """
    Менеджер индивидуального браузера для Stateful сессии.
    
    Использование:
        manager = SessionBrowserManager(config)
        page = await manager.init()
        # ... работа с page ...
        await manager.close()
    """
    
    def __init__(self, config: SessionConfig):
        """
        Инициализировать менеджер сессии.
        
        Args:
            config: Конфигурация сессии (прокси, headless, user_agent, etc.)
        """
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
    
    async def init(self) -> Page:
        """
        Инициализировать Playwright, браузер и страницу.
        
        Returns:
            Page объект для взаимодействия
        """
        logger.info(f"Initializing session browser (headless={self.config.headless})")
        
        # Запуск Playwright
        self._playwright = await async_playwright().start()
        
        # Настройка прокси
        proxy_settings = None
        if self.config.proxy:
            proxy_settings = {"server": self.config.proxy}
            logger.info(f"Using proxy: {self._mask_proxy(self.config.proxy)}")
        
        # Запуск браузера
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            proxy=proxy_settings,
        )
        
        # Настройка контекста
        context_options = {
            "viewport": {
                "width": self.config.window_size.get("width", 1920),
                "height": self.config.window_size.get("height", 1080),
            },
        }
        
        if self.config.user_agent:
            context_options["user_agent"] = self.config.user_agent
        
        self._context = await self._browser.new_context(**context_options)
        
        # Создание страницы
        self._page = await self._context.new_page()
        
        # Установка таймаутов
        self._page.set_default_timeout(settings.PLAYWRIGHT_TIMEOUT_SECONDS)
        
        logger.info("Session browser initialized successfully")
        
        return self._page
    
    async def close(self) -> None:
        """
        Закрыть страницу, контекст, браузер и Playwright.
        Освобождает все ресурсы.
        """
        logger.info("Closing session browser...")
        
        try:
            if self._page:
                await self._page.close()
                self._page = None
            
            if self._context:
                await self._context.close()
                self._context = None
            
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            
            logger.info("Session browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing session browser: {e}")
    
    @property
    def page(self) -> Optional[Page]:
        """Получить Page объект"""
        return self._page
    
    @property
    def is_active(self) -> bool:
        """Проверить, активна ли сессия"""
        return self._page is not None and not self._page.is_closed()
    
    @staticmethod
    def _mask_proxy(proxy: str) -> str:
        """Замаскировать прокси для логирования"""
        if "@" in proxy:
            prefix, rest = proxy.split("@", 1)
            return f"{prefix.split('://')[0]}://***@{rest}"
        return proxy
