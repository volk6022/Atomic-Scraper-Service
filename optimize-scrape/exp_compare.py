"""Experiment: bytes-over-wire + content retention per method, per domain.

Three methods per URL:
  1. httpx_ssr     — proxied httpx GET (+URL rewrites t.me/s, m.vk.com), SSR text
  2. browser_block — Playwright goto with image/media/font/stylesheet aborted
  3. browser_full  — Playwright goto, nothing blocked (current production path)

We measure *wire* bytes via Playwright `request.sizes().responseBodySize` (encoded)
for the browser, and `resp.num_bytes_downloaded` for httpx. Content retention is
the extracted-text word count + presence of key signals (phone / social / block-wall).

Run from repo root so proxies.txt + src imports resolve:
  .venv/Scripts/python.exe optimize-scrape/exp_compare.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.domain.utils.content_cleaner import html_to_text, count_words  # noqa: E402
from src.infrastructure.browser.pool_manager import pool_manager  # noqa: E402
from src.infrastructure.browser.proxy_provider import proxy_provider  # noqa: E402
from src.infrastructure.browser.user_agent_pool import UserAgentPool  # noqa: E402

# Reuse the battle-tested proxy rotation + URL builder from the yandex SSR path.
from src.actions.yandex_maps import (  # noqa: E402
    _build_proxy_url, _httpx_proxy, _DEAD_PROXIES, _mark_proxy_dead,
)
import time as _time  # noqa: E402


def _browser_proxy(tries_pool: int = 30):
    """Pick a proxy DICT (browser form) skipping recently-dead ports."""
    now = _time.monotonic()
    fallback = None
    for _ in range(tries_pool):
        p = proxy_provider.get_proxy()
        if not p:
            return None, None
        url = _build_proxy_url(p)
        fallback = (p, url)
        if _DEAD_PROXIES.get(url, 0.0) <= now:
            return p, url
    return fallback if fallback else (None, None)

BLOCK_TYPES = {"image", "media", "font", "stylesheet"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# Curated real URLs (from the 132-org run). 2 per top domain.
URLS = [
    ("t.me",          "https://t.me/maximumauto"),
    ("t.me",          "https://t.me/Parikmakherskaya1"),
    ("vk.com",        "https://vk.com/club32063264"),
    ("vk.com",        "https://vk.com/public194067229"),
    ("instagram.com", "https://www.instagram.com/pobokalam.spb/"),
    ("2gis.ru",       "https://2gis.ru/spb/firm/5348552838715575"),
    ("zoon.ru",       "https://zoon.ru/spb/restaurants/restoran_po_bokalam_na_klinskom_prospekte/"),
    ("zoon.ru",       "https://zoon.ru/spb/education/shkola_no5/"),
    ("spb.hh.ru",     "https://spb.hh.ru/employer/224317"),
    ("prodoctorov.ru","https://prodoctorov.ru/spb/lpu/61561-stomatologiya-doktora-budovskogo/"),
    ("rusprofile.ru", "https://www.rusprofile.ru/id/2556112"),
    ("rubrikator.org","https://rubrikator.org/russia/saint-petersburg/parikmaherskaya-no1"),
    ("orgzz.ru",      "https://orgzz.ru/spb/co/produktovyy_magazin/5523403"),
    ("spb.spravker.ru","https://spb.spravker.ru/medtsentryi-i-kliniki/say-me.htm"),
]

PHONE_RE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
HANDLE_RE = re.compile(r"@[A-Za-z0-9_.]{3,}")
BLOCK_MARKERS = ("smartcaptcha", "showcaptcha", "captcha", "log in", "войдите",
                 "log into instagram", "are you a robot", "доступ ограничен",
                 "проверка", "checking your browser")


def rewrite(url: str) -> str:
    """Cheap SSR-friendly rewrites for httpx fetch."""
    p = urlparse(url)
    host = p.netloc.lower()
    if host in ("t.me", "www.t.me"):
        # t.me/X -> t.me/s/X (public web preview, pure SSR)
        path = p.path
        if path and not path.startswith("/s/") and len(path.strip("/")) > 0:
            return f"https://t.me/s{path}"
    if host in ("vk.com", "www.vk.com"):
        return f"https://m.vk.com{p.path}"
    return url


def signals(text: str, raw_lower: str) -> dict:
    return {
        "phone": bool(PHONE_RE.search(text)),
        "handle": bool(HANDLE_RE.search(text)),
        "blocked": any(m in raw_lower for m in BLOCK_MARKERS),
    }


async def fetch_httpx(url: str, tries: int = 8) -> dict:
    rurl = rewrite(url)
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=20.0)
    last = None
    t0 = time.time()
    for _ in range(tries):
        proxy = _httpx_proxy()
        try:
            async with httpx.AsyncClient(
                proxy=proxy, headers=HEADERS, timeout=timeout, follow_redirects=True
            ) as c:
                resp = await c.get(rurl)
                wire = resp.num_bytes_downloaded
                html = resp.text
                text = html_to_text(html)
                low = html.lower()
                return {
                    "ok": True, "status": resp.status_code, "wire_bytes": wire,
                    "html_bytes": len(html.encode("utf-8", "ignore")),
                    "words": count_words(text), "elapsed": round(time.time() - t0, 1),
                    "rewritten": rurl if rurl != url else None,
                    **signals(text, low),
                }
        except Exception as e:  # noqa: BLE001
            last = e
    return {"ok": False, "error": str(last)[:160], "elapsed": round(time.time() - t0, 1)}


async def fetch_browser(url: str, block: bool, tries: int = 8) -> dict:
    ua = UserAgentPool().get_user_agent()
    last = None
    for _ in range(tries):
        proxy, purl = _browser_proxy()
        t0 = time.time()
        context = None
        try:
            context = await pool_manager.create_context(
                user_agent=ua, stealth=True, proxy=proxy,
                locale="ru-RU", timezone_id="Europe/Moscow",
            )
            wire = {"n": 0}
            blocked_n = {"n": 0}
            pending = []

            if block:
                async def _route(route, request):
                    if request.resource_type in BLOCK_TYPES:
                        blocked_n["n"] += 1
                        try:
                            await route.abort()
                        except Exception:
                            pass
                    else:
                        try:
                            await route.continue_()
                        except Exception:
                            pass
                await context.route("**/*", _route)

            page = await context.new_page()

            def on_finished(request):
                async def _add():
                    try:
                        s = await request.sizes()
                        wire["n"] += (s.get("responseBodySize", 0) or 0) + \
                                     (s.get("responseHeadersSize", 0) or 0)
                    except Exception:
                        pass
                pending.append(asyncio.create_task(_add()))
            page.on("requestfinished", on_finished)

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.2)  # let late requests fire
            html = await page.content()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            text = html_to_text(html)
            low = html.lower()
            return {
                "ok": True, "wire_bytes": wire["n"], "blocked_reqs": blocked_n["n"],
                "html_bytes": len(html.encode("utf-8", "ignore")),
                "words": count_words(text), "elapsed": round(time.time() - t0, 1),
                **signals(text, low),
            }
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e).lower()
            if "tunnel" in msg or "timeout" in msg or "proxy" in msg or "reset" in msg:
                _mark_proxy_dead(purl)
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
    return {"ok": False, "error": str(last)[:160]}


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = []
    for dom, url in URLS:
        if only and only not in dom:
            continue
        print(f"\n=== {dom}  {url}")
        h = await fetch_httpx(url)
        print(f"  httpx_ssr   : {h}")
        b = await fetch_browser(url, block=True)
        print(f"  browser_blk : {b}")
        f = await fetch_browser(url, block=False)
        print(f"  browser_full: {f}")
        results.append({"domain": dom, "url": url,
                        "httpx": h, "browser_block": b, "browser_full": f})
    out = ROOT / "optimize-scrape" / "exp_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    await pool_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
