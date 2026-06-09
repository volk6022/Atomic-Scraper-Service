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
    """Scrape a URL and return cleaned text.

    Routing (cheapest viable method wins; see ``optimize-scrape/FINDINGS.md``):
      1. Instagram → login-walled, never render: return a light @-handle stub.
      2. Allowlisted SSR domains → proxied httpx GET (~15-40x fewer bytes than a
         browser, equal content). Falls back to the browser if httpx fails/blocks.
      3. Everything else → Playwright browser via ``SiteEnrichAction`` (with
         in-browser resource-blocking), retried across fresh rotating proxies.
    """
    from src.actions.research.http_fetch import (
        host_in_allowlist,
        httpx_ssr_fetch,
        instagram_handle,
        is_instagram,
    )
    from src.domain.utils.content_cleaner import count_words, html_to_text

    # 1. Instagram: login-wall — return the handle from the URL, don't render.
    if is_instagram(url):
        handle = instagram_handle(url)
        text = f"Instagram profile @{handle}" if handle else "Instagram (login-walled; no public content)"
        return {"url": url, "text": text, "word_count": len(text.split()),
                "success": True, "method": "instagram_stub"}

    # 2. httpx-SSR fast-path for allowlisted server-rendered domains.
    if host_in_allowlist(url):
        try:
            html = await httpx_ssr_fetch(url)
            text = html_to_text(html)[:30000]  # let goal-extract pick from the full page
            return {"url": url, "text": text, "word_count": count_words(text),
                    "success": True, "method": "httpx_ssr"}
        except Exception as e:  # noqa: BLE001 — fall back to the browser path
            logger.warning("httpx_ssr fast-path failed for %s (%s) — browser fallback", url, e)

    # 3. Browser path (heavy SPAs, org sites, social profiles).
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
                "method": "browser",
            }
        except Exception as e:  # noqa: BLE001 — retry transient proxy/nav failures
            last_err = e
            logger.warning("scrape_url attempt %d/%d failed %s: %s",
                           attempt, attempts, url, e)
    return {"url": url, "error": str(last_err), "success": False}
