"""Approach #2 — Playwright headless Chromium (no stealth)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from playwright.async_api import async_playwright

from ..parser import looks_blocked, parse_serp_html
from ..proxy_forwarder import PlaywrightProxySource
from ..session_helpers import session_storage_state_path


class BlockedError(RuntimeError):
    pass


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


async def fetch_serp(
    query: str,
    *,
    proxy_url: str | None = None,
    session: dict[str, Any] | None = None,
    num: int = 10,
    timeout_ms: int = 45000,
) -> dict[str, Any]:
    params = {"q": query, "num": num, "hl": "en", "gl": "us", "pws": 0}
    url = "https://www.google.com/search?" + urlencode(params)

    # session implicitly carries proxy_url; explicit arg wins if both set
    effective_proxy = proxy_url
    if session and not effective_proxy:
        effective_proxy = session.get("proxy_url")
    storage_state = session_storage_state_path(session)

    async with PlaywrightProxySource(effective_proxy) as pw_proxy:
        launch_kwargs: dict[str, Any] = {"headless": True}
        if pw_proxy:
            launch_kwargs["proxy"] = pw_proxy

        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_kwargs)
            try:
                context_kwargs: dict[str, Any] = dict(
                    user_agent=USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                if storage_state:
                    context_kwargs["storage_state"] = storage_state

                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_selector(
                        "div.tF2Cxc, div.yuRUbf, h3", timeout=8000
                    )
                except Exception:
                    pass
                final_url = page.url
                html = await page.content()
            finally:
                await browser.close()

    if "/sorry/" in final_url or looks_blocked(html):
        raise BlockedError("captcha / sorry page")
    return parse_serp_html(html, query, num=num)
