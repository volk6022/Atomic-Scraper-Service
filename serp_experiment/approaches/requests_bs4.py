"""Approach #1 — requests + BeautifulSoup (no JS rendering)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests

from ..parser import looks_blocked, parse_serp_html

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}


class BlockedError(RuntimeError):
    pass


def fetch_serp(
    query: str,
    *,
    proxy_url: str | None = None,
    num: int = 10,
    timeout: float = 20.0,
) -> dict[str, Any]:
    params = {"q": query, "num": num, "hl": "en", "gl": "us", "pws": 0}
    url = "https://www.google.com/search?" + urlencode(params)
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    # Pre-set Google consent cookies so we don't get redirected to a
    # consent-flow interstitial.
    cookies = {
        "CONSENT": "YES+cb",
        "SOCS": "CAESHAgBEhIaAmVuIAEaBgiAuI6vBg",
    }

    resp = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        cookies=cookies,
        proxies=proxies,
        timeout=timeout,
        allow_redirects=True,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"http {resp.status_code}")
    if looks_blocked(resp.text) or "/sorry/" in resp.url:
        raise BlockedError("captcha / consent / sorry page")

    return parse_serp_html(resp.text, query, num=num)
