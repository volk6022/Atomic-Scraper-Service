import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext
from src.infrastructure.browser.stealth_pool import stealth_pool
from src.infrastructure.browser.user_agent_pool import user_agent_pool


class BrowserPoolManager:
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    def available_contexts(self) -> int:
        """Return count of available browser contexts."""
        return 1 if self._browser else 0

    async def get_browser(self, proxy: Optional[str] = None) -> Browser:
        async with self._lock:
            if self._browser is None:
                self._playwright = await async_playwright().start()

                launch_options = {"headless": True}

                if proxy:
                    launch_options["proxy"] = {"server": proxy}

                self._browser = await self._playwright.chromium.launch(**launch_options)
            return self._browser

    async def create_context(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        stealth: bool = False,
        **kwargs,
    ) -> BrowserContext:
        if stealth:
            if not user_agent:
                user_agent = user_agent_pool.get_user_agent()

            context = await stealth_pool.create_context(user_agent=user_agent)

            if proxy:
                await context.set_proxy(**{"server": proxy})

            return context

        browser = await self.get_browser(proxy=proxy)

        context_options = {}

        if user_agent:
            context_options["user_agent"] = user_agent

        if proxy:
            context_options["proxy"] = {"server": proxy}

        context_options.update(kwargs)

        return await browser.new_context(**context_options)

    async def close(self):
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


pool_manager = BrowserPoolManager()
