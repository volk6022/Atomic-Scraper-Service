"""Web tools for the flat-loop research agent.

Two plain async functions the agent calls directly (no LangChain dispatcher):
``web_search`` (SearXNG via ``SearXngSearchClient``) and ``scrape_url``
(Playwright + proxy + stealth via ``SiteEnrichAction``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def web_search(query: str, k: int = 5, language: str | None = None) -> list[dict]:
    """Web search via local SearXNG (backed by ``SearXngSearchClient``).

    ``language`` is a BCP-47 / SearXNG language hint ("ru", "en"). When set,
    SearXNG biases the engine map and the returned SERP becomes overwhelmingly
    that language — main lever for getting local results without proxies.

    On failure returns ``[]`` (not an error dict) so callers don't have to
    special-case error sentinels mixed in with real results.
    """
    from src.core.logging import get_logger
    from src.domain.models.requests import SearchRequest
    from src.infrastructure.external_api.search_client import search_client

    log = get_logger(__name__)
    try:
        request = SearchRequest(q=query, num=k)
        response = await search_client.search(request, language=language)
        return [
            {"url": r.link, "title": r.title, "snippet": r.snippet}
            for r in response.organic
        ]
    except Exception as e:
        log.error("web_search failed for %r: %s", query, e)
        return []


async def scrape_url(url: str, *, attempts: int = 2) -> dict:
    """Scrape a URL via SiteEnrichAction and return cleaned text.

    Retries on failure (default 2 attempts) — each ``SiteEnrichAction()`` picks a
    fresh rotating proxy, so a flaky/dead proxy on the first try is routed around.
    """
    from src.actions.site_enricher import SiteEnrichAction

    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        action = SiteEnrichAction()
        try:
            result = await action.execute(url)
            return {
                "url": url,
                "text": result.text,
                "word_count": len(result.text.split()),
                "success": True,
            }
        except Exception as e:  # noqa: BLE001 — retry transient proxy/nav failures
            last_err = e
            logger.warning("scrape_url attempt %d/%d failed %s: %s",
                           attempt, attempts, url, e)
    return {"url": url, "error": str(last_err), "success": False}
