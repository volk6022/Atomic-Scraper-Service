"""Yandex Maps actions — XHR-intercept strategy.

Implements two actions, both derived from the experiments in
`yandex_maps_experiment/` (see `docs/yandex-maps-scraping-experiment-journal.md`):

* :class:`YandexMapsExtractAction` — discovery. Launches a headless browser
  through a residential proxy, navigates to a regional search URL, intercepts
  responses to ``/maps/api/search``, and parses ``data.items[]`` to build
  :class:`YandexOrganization` objects (65+ fields per org including
  phones/coordinates/services/photos/metro/ИНН).

* :class:`YandexMapsReviewsAction` — reviews. Same browser session pattern,
  but observes ``/maps/api/business/fetchReviews`` URLs, then replays them
  via ``page.request.get(...)`` to authenticate against the same-origin
  endpoint with live session cookies.

Both actions are registered in :data:`action_registry`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import quote

from src.core.logging import get_logger
from src.domain.models.dsl import CommandType
from src.domain.models.yandex_organization import YandexOrganization
from src.domain.models.yandex_review import YandexReview
from src.domain.registry.action_registry import action_registry
from src.infrastructure.browser.pool_manager import BrowserPoolManager
from src.infrastructure.browser.proxy_provider import proxy_provider
from src.infrastructure.browser.user_agent_pool import UserAgentPool

logger = get_logger(__name__)


class YandexCaptchaError(RuntimeError):
    """Raised when Yandex SmartCaptcha is detected on the loaded page."""


# Endpoints that the search results SPA hits with org payloads.
_SEARCH_API_MARKERS = (
    "/maps/api/search",
    "search-maps.yandex.ru/v1",
    "fullobjects",
)
# Endpoint that the org reviews tab hits for review pages.
_REVIEWS_API_MARKER = "fetchReviews"

# Paths inside the `/maps/api/search` JSON that may hold the array of orgs.
_SEARCH_ITEMS_PATHS: tuple[tuple[str, ...], ...] = (
    ("data", "items"),
    ("items",),
    ("data", "geo", "items"),
)
# Paths inside the `fetchReviews` JSON that may hold the array of reviews.
_REVIEW_ITEMS_PATHS: tuple[tuple[str, ...], ...] = (
    ("data", "reviews"),
    ("reviews",),
    ("data", "items"),
    ("items",),
)


def _get_in(data: Any, path: tuple[str, ...]) -> Optional[Any]:
    cur = data
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _extract_array(data: Any, paths: tuple[tuple[str, ...], ...]) -> Optional[list]:
    for path in paths:
        cur = _get_in(data, path)
        if isinstance(cur, list):
            return cur
    return None


def _is_business_item(it: Any) -> bool:
    """`data.items` contains transit stops / metro stations too; we only want orgs."""
    if not isinstance(it, dict):
        return False
    return any(k in it for k in ("permalink", "seoname", "oid")) and bool(
        it.get("id") or it.get("oid") or it.get("businessId")
    )


class YandexMapsExtractAction:
    """Discovery: text-query search inside a region → list[YandexOrganization]."""

    def __init__(self) -> None:
        self.pool_manager = BrowserPoolManager()
        self.user_agent_pool = UserAgentPool()
        self.scroll_limit = 25
        self.scroll_pause_ms = 900
        self.captured_response_timeout = 10.0

    async def execute(
        self,
        query: str,
        region_id: int = 2,
        city_slug: str = "saint-petersburg",
        target_count: int = 40,
        include_raw: bool = True,
    ) -> list[YandexOrganization]:
        proxy = proxy_provider.get_proxy() or None
        user_agent = self.user_agent_pool.get_user_agent()
        logger.info(
            "yandex_maps.extract: query=%r region_id=%s city=%s target=%s proxy=%s",
            query, region_id, city_slug, target_count, bool(proxy),
        )

        context = await self.pool_manager.create_context(
            user_agent=user_agent,
            stealth=True,
            proxy=proxy,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )

        captured: list[dict[str, Any]] = []
        pending_tasks: list[asyncio.Task] = []

        async def _capture(resp) -> None:
            url = resp.url
            try:
                body = await resp.text()
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.debug("failed to read response body for %s: %s", url[:120], exc)
                return
            captured.append({"url": url, "status": resp.status, "body": body})
            logger.debug("captured XHR %s %s (%dB)", resp.status, url[:120], len(body))

        def on_response(resp) -> None:
            # `page.on("response", …)` is synchronous; schedule async work and
            # remember the task so we can drain it before the context closes.
            if any(m in resp.url for m in _SEARCH_API_MARKERS):
                pending_tasks.append(asyncio.create_task(_capture(resp)))

        try:
            page = await context.new_page()
            page.on("response", on_response)

            url = (
                f"https://yandex.ru/maps/{region_id}/{city_slug}/search/{quote(query, safe='')}/"
            )
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                logger.warning("page.goto failed: %s", exc)
                raise

            content_lower = (await page.content()).lower()
            if "smartcaptcha" in content_lower or "showcaptcha" in content_lower:
                raise YandexCaptchaError(f"captcha on initial load of {url}")

            try:
                await page.wait_for_selector(
                    ".search-list-view, .search-snippet-view", timeout=20_000
                )
            except Exception as exc:
                logger.warning("results panel never appeared: %s", exc)

            await self._scroll_until(page, target_count)

            # Drain pending body reads before closing the context (else
            # `resp.text()` will fail with "Target page, context or browser
            # has been closed").
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
        finally:
            try:
                await context.close()
            except Exception:
                pass

        orgs = self._parse_captured(captured, include_raw=include_raw)
        logger.info(
            "yandex_maps.extract: captured=%d unique_orgs=%d",
            len(captured), len(orgs),
        )
        return orgs

    async def _scroll_until(self, page, target_count: int) -> None:
        """DOM-scroll until either target reached or the list stops growing."""
        count_js = (
            "() => document.querySelectorAll("
            "'li.search-snippet-view, div.search-snippet-view'"
            ").length"
        )
        scroll_js = """() => {
            const list = document.querySelector(
                '.scroll__container, .search-list-view__list, .search-list-view'
            ) || document.querySelector('div[class*=search-list]');
            if (list) list.scrollBy(0, 2000);
            window.scrollBy(0, 1500);
        }"""

        seen, stale = 0, 0
        for _ in range(self.scroll_limit):
            try:
                count = await page.evaluate(count_js)
            except Exception:
                count = seen
            if count >= target_count:
                break
            if count == seen:
                stale += 1
                if stale >= 3:
                    break
            else:
                stale = 0
            seen = count
            try:
                await page.evaluate(scroll_js)
            except Exception:
                pass
            await page.wait_for_timeout(self.scroll_pause_ms)

    def _parse_captured(
        self, captured: list[dict[str, Any]], *, include_raw: bool
    ) -> list[YandexOrganization]:
        orgs: list[YandexOrganization] = []
        seen_oids: set[str] = set()

        for cap in captured:
            body = cap.get("body") or ""
            if len(body) < 80:
                continue
            try:
                data = json.loads(body)
            except Exception:
                continue

            items = _extract_array(data, _SEARCH_ITEMS_PATHS)
            if not items:
                continue

            for raw_item in items:
                if not _is_business_item(raw_item):
                    continue
                oid = str(
                    raw_item.get("id") or raw_item.get("oid") or raw_item.get("businessId") or ""
                )
                if not oid or oid in seen_oids:
                    continue
                try:
                    org = YandexOrganization.from_yandex_item(raw_item, keep_raw=include_raw)
                except Exception as exc:
                    logger.debug("skipping malformed org item oid=%s: %s", oid, exc)
                    continue
                seen_oids.add(oid)
                orgs.append(org)

        return orgs


class YandexMapsReviewsAction:
    """Reviews: observe `fetchReviews` URL, replay via same browser session."""

    def __init__(self) -> None:
        self.pool_manager = BrowserPoolManager()
        self.user_agent_pool = UserAgentPool()
        self.scroll_iterations = 5
        self.scroll_pause_ms = 1200

    async def execute(
        self,
        business_oid: str,
        seoname: str,
        count: int = 50,
        ranking: str = "by_time",
        pages: int = 1,
        include_raw: bool = True,
    ) -> list[YandexReview]:
        proxy = proxy_provider.get_proxy() or None
        user_agent = self.user_agent_pool.get_user_agent()
        logger.info(
            "yandex_maps.reviews: oid=%s seoname=%s count=%s ranking=%s pages=%s",
            business_oid, seoname, count, ranking, pages,
        )

        context = await self.pool_manager.create_context(
            user_agent=user_agent,
            stealth=True,
            proxy=proxy,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )

        observed_urls: list[str] = []

        def on_response(resp) -> None:
            if _REVIEWS_API_MARKER in resp.url and resp.status == 200:
                observed_urls.append(resp.url)

        org_url = f"https://yandex.ru/maps/org/{seoname}/{business_oid}/reviews/"
        all_reviews: list[dict[str, Any]] = []

        try:
            page = await context.new_page()
            page.on("response", on_response)

            try:
                await page.goto(org_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                logger.warning("page.goto reviews failed: %s", exc)
                raise

            content_lower = (await page.content()).lower()
            if "smartcaptcha" in content_lower or "showcaptcha" in content_lower:
                raise YandexCaptchaError(f"captcha on reviews page {org_url}")

            try:
                await page.wait_for_selector(
                    ".business-reviews-card-view, .business-review-view, .scroll__container",
                    timeout=20_000,
                )
            except Exception as exc:
                logger.debug("reviews ui not detected: %s", exc)

            await self._scroll_reviews_pane(page)
            # Let the last batch of `fetchReviews` XHRs land in our observer.
            await asyncio.sleep(1.5)

            # Replay each observed URL via the live session — this is what the
            # research found to be the only reliable way to read the full body
            # (param ordering & cookies must match exactly).
            seen_urls: set[str] = set()
            for u in observed_urls[: max(1, pages)]:
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                try:
                    resp = await page.request.get(
                        u,
                        headers={
                            "Referer": org_url,
                            "Accept": "application/json, text/plain, */*",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        timeout=30_000,
                    )
                except Exception as exc:
                    logger.warning("fetchReviews replay failed for %s: %s", u[:120], exc)
                    continue

                if resp.status != 200:
                    logger.warning("fetchReviews replay %s -> %s", u[:120], resp.status)
                    continue

                try:
                    data = await resp.json()
                except Exception as exc:
                    logger.warning("fetchReviews replay JSON parse failed: %s", exc)
                    continue

                items = _extract_array(data, _REVIEW_ITEMS_PATHS)
                if items:
                    all_reviews.extend(items)
        finally:
            try:
                await context.close()
            except Exception:
                pass

        reviews = self._dedup_reviews(all_reviews, include_raw=include_raw)
        logger.info(
            "yandex_maps.reviews: observed=%d unique_reviews=%d",
            len(observed_urls), len(reviews),
        )
        return reviews

    async def _scroll_reviews_pane(self, page) -> None:
        scroll_js = """() => {
            const c = document.querySelector(
                '.scroll__container, .business-reviews-card-view, div[class*=reviews]'
            );
            if (c) c.scrollBy(0, 4000);
            window.scrollBy(0, 3000);
        }"""
        for _ in range(self.scroll_iterations):
            try:
                await page.evaluate(scroll_js)
            except Exception:
                pass
            await page.wait_for_timeout(self.scroll_pause_ms)

    def _dedup_reviews(
        self, items: list[dict[str, Any]], *, include_raw: bool
    ) -> list[YandexReview]:
        seen: set[str] = set()
        out: list[YandexReview] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            rid = str(raw.get("reviewId") or raw.get("id") or raw.get("publicId") or "")
            if not rid or rid in seen:
                continue
            try:
                review = YandexReview.from_yandex_item(raw, keep_raw=include_raw)
            except Exception as exc:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("skipping malformed review %s: %s", rid, exc)
                continue
            seen.add(rid)
            out.append(review)
        return out


action_registry.register(CommandType.YANDEX_MAPS_EXTRACT)(YandexMapsExtractAction)
action_registry.register(CommandType.YANDEX_MAPS_REVIEWS)(YandexMapsReviewsAction)
