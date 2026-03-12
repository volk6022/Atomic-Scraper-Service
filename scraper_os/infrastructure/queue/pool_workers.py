"""
infrastructure/queue/pool_workers.py — Stateless scraping tasks.

Implements the /scrape and /serper task logic using the global
BrowserPoolManager.
"""

import logging
from scraper_os.infrastructure.queue.broker import broker
from scraper_os.infrastructure.browser.pool_manager import BrowserPoolManager
from scraper_os.domain.models.requests import ScrapeRequest, SerperSearchRequest
from scraper_os.domain.models.dsl import ScrapeResult, SerperResult
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


@broker.task
async def scrape_task(request: ScrapeRequest) -> ScrapeResult:
    """Atomic scraping task.

    Creates a new context, navigates, waits, and extracts content.
    """
    proxy = settings.next_proxy()
    logger.info("Executing scrape_task for %s using proxy %s", request.url, proxy)

    context = await BrowserPoolManager.new_context(
        proxy=proxy, extra_http_headers=request.headers
    )
    page = await context.new_page()

    try:
        response = await page.goto(
            request.url, timeout=request.timeout_ms, wait_until="networkidle"
        )

        if request.wait_for:
            await page.wait_for_selector(request.wait_for, timeout=request.timeout_ms)

        content = (
            await page.content()
            if not request.extract_text
            else await page.evaluate("() => document.body.innerText")
        )

        return ScrapeResult(
            url=request.url,
            html=content if not request.extract_text else None,
            text=content if request.extract_text else None,
            status_code=response.status if response else None,
        )
    except Exception as exc:
        logger.error("Scrape failed: %s", exc)
        return ScrapeResult(url=request.url, error=str(exc))
    finally:
        await context.close()


@broker.task
async def serper_task(request: SerperSearchRequest) -> SerperResult:
    """Search task (scraping Google)."""
    proxy = settings.next_proxy()
    logger.info(
        "Executing serper_task for query: %s using proxy %s", request.query, proxy
    )

    context = await BrowserPoolManager.new_context(proxy=proxy)
    page = await context.new_page()

    try:
        # Navigate to Google Search
        search_url = (
            f"https://www.google.com/search?q={request.query}&num={request.num_results}"
        )
        await page.goto(search_url, wait_until="networkidle")

        # Basic parsing of search results
        results = await page.evaluate("""
            () => {
                const items = [];
                const nodes = document.querySelectorAll('div.g');
                for (const node of nodes) {
                    const titleNode = node.querySelector('h3');
                    const linkNode = node.querySelector('a');
                    const snippetNode = node.querySelector('div.VwiC3b');
                    
                    if (titleNode && linkNode) {
                        items.push({
                            title: titleNode.innerText,
                            url: linkNode.href,
                            snippet: snippetNode ? snippetNode.innerText : ""
                        });
                    }
                }
                return items;
            }
        """)

        return SerperResult(query=request.query, results=results[: request.num_results])
    except Exception as exc:
        logger.error("Serper search failed: %s", exc)
        return SerperResult(query=request.query, error=str(exc))
    finally:
        await context.close()
