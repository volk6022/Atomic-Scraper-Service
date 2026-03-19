import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext
from src.core.config import settings


class BrowserPoolManager:
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def get_browser(self) -> Browser:
        async with self._lock:
            if self._browser is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            return self._browser

    async def create_context(self, **kwargs) -> BrowserContext:
        browser = await self.get_browser()
        return await browser.new_context(**kwargs)

    async def close(self):
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


pool_manager = BrowserPoolManager()
