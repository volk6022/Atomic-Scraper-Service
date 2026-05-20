"""Approach #4 — local SearXNG meta-search (JSON API).

SearXNG аккумулирует выдачу нескольких поисковиков (Google, Brave, Bing, ...)
и сам разбирается с прокси/анти-бот защитами на стороне инстанса. Для нашего
скрипта это «бесплатный» путь — стучимся локально по HTTP.

Endpoint: ``GET http://localhost:8080/search?q=<query>&format=json``
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests


DEFAULT_BASE = "http://localhost:8080"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_serp(
    query: str,
    *,
    proxy_url: str | None = None,
    num: int = 10,
    timeout: float = 30.0,
    base_url: str = DEFAULT_BASE,
) -> dict[str, Any]:
    """Return Serper-compatible SERP dict from local SearXNG."""
    # proxy_url игнорируется для локального инстанса (но принимаем для совместимости
    # сигнатуры с остальными подходами).
    params = {"q": query, "format": "json", "language": "en"}
    url = f"{base_url.rstrip('/')}/search?" + urlencode(params)

    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"searxng http {resp.status_code}")

    data = resp.json()
    raw = data.get("results") or []

    organic: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        link = item.get("url") or ""
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        organic.append(
            {
                "title": (item.get("title") or "").strip(),
                "link": link,
                "snippet": (item.get("content") or "").strip(),
                "position": len(organic) + 1,
            }
        )
        if len(organic) >= num:
            break

    return {
        "searchParameters": {
            "q": query,
            "type": "search",
            "engine": "searxng",
            "num": num,
        },
        "organic": organic,
    }
