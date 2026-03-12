"""
infrastructure/browser/session_manager.py — Isolated Playwright instance for Stateful Actors.

Circuit B: Stateful Actors.
Each actor process owns its own Playwright instance and Browser.
This ensures total isolation and prevents one failing session from
affecting others.
"""

import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from scraper_os.domain.models.requests import SessionConfig

logger = logging.getLogger(__name__)


class SessionBrowserManager:
    """Manages an isolated browser instance for a single stateful session."""

    def __init__(self, config: SessionConfig):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def init(self) -> Page:
        """Launch the private browser and create the primary page."""
        logger.info("Initializing isolated browser for stateful session...")

        self._playwright = await async_playwright().start()

        # Proxy for stateful sessions is provided by the client
        proxy_settings = {"server": self.config.proxy} if self.config.proxy else None

        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            proxy=proxy_settings,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )

        self._context = await self._browser.new_context(
            user_agent=self.config.user_agent,
            viewport=self.config.window_size,
        )

        self._page = await self._context.new_page()
        logger.info("Isolated session browser initialized.")
        return self._page

    async def close(self):
        """Clean up all resources."""
        logger.info("Closing isolated session browser...")
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Session cleanup complete.")
