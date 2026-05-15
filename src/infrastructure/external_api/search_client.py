import asyncio
import random
from typing import Optional, List
from urllib.parse import quote

from src.infrastructure.browser.stealth_pool import HumanEmulator

from src.core.logging import get_logger
from src.domain.models.requests import SearchRequest, SearchResponse, SearchResult
from src.infrastructure.browser.pool_manager import pool_manager
from src.infrastructure.browser.proxy_provider import proxy_provider

logger = get_logger(__name__)


class GoogleSearchClient:
    def __init__(self, proxy_provider=None):
        self._proxy_provider = proxy_provider

    async def _search_with_browser(
        self, query: str, proxy: Optional[str] = None
    ) -> List[dict]:
        context = None
        try:
            context = await pool_manager.create_context(
                proxy=proxy, headless=True, stealth=True
            )
            page = await context.new_page()

            search_url = f"https://www.google.com/search?q={quote(query)}"
            logger.info(f"Navigating to Google search: {query}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)

            # Detect CAPTCHA immediately — before wasting 20s on selectors
            if "/sorry/" in page.url or "captcha" in (await page.title()).lower():
                raise Exception("Google CAPTCHA detected")

            try:
                await page.wait_for_selector("[data-rpos]", timeout=10000)
            except Exception:
                try:
                    await page.wait_for_selector(".g", timeout=5000)
                except Exception:
                    await page.wait_for_selector("#search", timeout=5000)

            await asyncio.sleep(random.uniform(1.5, 4.0))
            await HumanEmulator.random_scroll(page)

            results = []
            result_containers = await page.locator("[data-rpos]").all()

            if not result_containers:
                result_containers = await page.locator(".g").all()
            if not result_containers:
                result_containers = await page.locator(".Gx5Nad").all()
            if not result_containers:
                result_containers = await page.locator(".VWHQLd").all()

            logger.info(f"Found {len(result_containers)} result containers")

            for container in result_containers:
                try:
                    idx = await container.get_attribute("data-rpos")
                    idx = int(idx) if idx else len(results) + 1

                    title_el = container.locator("h3").first
                    link_el = container.locator("a[ping]").first
                    snippet_el = container.locator(".VwiC3b, .st, [data-sncf]").first

                    title = (
                        await title_el.text_content()
                        if await title_el.count() > 0
                        else ""
                    )
                    href = (
                        await link_el.get_attribute("href")
                        if await link_el.count() > 0
                        else ""
                    )
                    snippet = (
                        await snippet_el.text_content()
                        if await snippet_el.count() > 0
                        else ""
                    )

                    if title and href:
                        results.append(
                            {
                                "title": title.strip(),
                                "link": href.strip(),
                                "snippet": snippet.strip() if snippet else "",
                                "position": idx,
                            }
                        )
                except Exception as e:
                    logger.debug(f"Failed to extract result: {e}")
                    continue

            if not results:
                results = await self._fallback_extraction(page)

            await page.close()
            await context.close()

            return results

        except Exception as e:
            logger.error(f"Google search failed: {e}")
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            raise Exception(f"Google search failed: {str(e)}")

    async def _fallback_extraction(self, page) -> List[dict]:
        results = []
        try:
            titles = await page.locator("h3").all()
            for idx, title_el in enumerate(titles[:20], start=1):
                try:
                    title = await title_el.text_content()
                    results.append(
                        {
                            "title": title.strip() if title else "",
                            "link": "",
                            "snippet": "",
                            "position": idx,
                        }
                    )
                except Exception:
                    continue
        except Exception:
            pass
        return results

    async def search(self, request: SearchRequest) -> SearchResponse:
        proxy = self._proxy_provider.get_proxy() if self._proxy_provider else None
        logger.info(f"Starting Google search for: {request.q}, proxy: {bool(proxy)}")

        try:
            raw_results = await self._search_with_browser(request.q, proxy)
        except Exception as e:
            # Retry with a fresh proxy rotation (new exit IP), never fallback to no-proxy
            retry_proxy = self._proxy_provider.get_proxy() if self._proxy_provider else proxy
            logger.warning(f"Browser search failed ({e}), retrying with fresh proxy rotation")
            try:
                raw_results = await self._search_with_browser(request.q, retry_proxy)
            except Exception as e2:
                logger.error(f"Both proxy attempts failed: {e2}")
                raise Exception(
                    "Google search blocked or failed. Use residential proxies."
                )

        organic = [
            SearchResult(
                title=r["title"],
                link=r["link"],
                snippet=r["snippet"],
                position=r["position"],
            )
            for r in raw_results[: request.num]
        ]

        return SearchResponse(
            searchParameters={
                "q": request.q,
                "type": "search",
                "engine": "google",
                "num": request.num,
            },
            organic=organic,
        )


SearchClient = GoogleSearchClient
search_client = GoogleSearchClient(proxy_provider=proxy_provider)
