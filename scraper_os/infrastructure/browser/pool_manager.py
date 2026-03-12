"""
infrastructure/browser/pool_manager.py — Global Playwright instance for stateless tasks.

Circuit A: Stateless Pool.
A single Playwright browser instance is shared across the worker process.
Each task creates a fresh, isolated BrowserContext.
"""

import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


class BrowserPoolManager:
    """Manages a persistent browser instance for a worker process."""

    _playwright = None
    _browser: Optional[Browser] = None

    @classmethod
    async def start(cls):
        """Initialize the browser. Called once per worker process."""
        if cls._browser is not None:
            return

        logger.info("Starting global Playwright browser for stateless pool...")
        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch(
            headless=settings.browser_headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        logger.info("Stateless browser started.")

    @classmethod
    async def stop(cls):
        """Close the browser. Called on worker shutdown."""
        if cls._browser:
            logger.info("Closing stateless browser...")
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

    @classmethod
    async def get_browser(cls) -> Browser:
        """Get the shared browser instance, starting it if necessary."""
        if cls._browser is None:
            await cls.start()
        return cls._browser

    @classmethod
    async def new_context(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        viewport: Optional[dict] = None,
        extra_http_headers: Optional[dict] = None,
    ) -> BrowserContext:
        """Create a new isolated context with optional proxy/UA settings."""
        if self._browser is None:
            await self.start()

        proxy_settings = {"server": proxy} if proxy else None

        return await self._browser.new_context(
            proxy=proxy_settings,
            user_agent=user_agent or settings.default_user_agent,
            viewport=viewport
            or {
                "width": settings.default_viewport_width,
                "height": settings.default_viewport_height,
            },
            extra_http_headers=extra_http_headers,
        )
