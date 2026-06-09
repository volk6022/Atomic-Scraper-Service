"""A/B validation on real orgs: OLD scrape path vs NEW, per the plan's §8.

For N orgs we replay their ACTUAL visited URLs (from data_750m/research_final)
through both paths and measure traffic (MB/org) + content retention:

  OLD path  = browser for every URL, NO resource-block, no httpx, no IG stub
              (i.e. the pre-change behaviour).
  NEW path  = the routing we shipped (http_fetch allowlist + IG stub + browser
              with resource-block for the rest), measured byte-for-byte.

This isolates the scrape-layer change (the only thing we touched) without the
variance of re-running the stochastic LLM agent. Bytes are wire bytes:
`request.sizes().responseBodySize` for the browser, `num_bytes_downloaded` for httpx.

t.me URLs are skipped: Telegram is unreachable from this host without VPN, which
would add symmetric noise to both arms.

Run from repo root: .venv/Scripts/python.exe optimize-scrape/ab_validation/ab_replay.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.actions.research.http_fetch import (  # noqa: E402
    host_in_allowlist, is_instagram, instagram_handle, rewrite_url,
)
from src.domain.utils.content_cleaner import html_to_text, count_words  # noqa: E402
from src.infrastructure.browser.pool_manager import pool_manager  # noqa: E402
from src.infrastructure.browser.proxy_provider import proxy_provider  # noqa: E402
from src.infrastructure.browser.user_agent_pool import UserAgentPool  # noqa: E402
from src.actions.yandex_maps import (  # noqa: E402
    _build_proxy_url, _httpx_proxy, _DEAD_PROXIES, _mark_proxy_dead,
)

# Ensure proxies load regardless of CWD.
if not getattr(proxy_provider, "_proxies", None):
    proxy_provider.proxy_file = ROOT / "proxies.txt"
    proxy_provider._load_proxies()

DATA = ROOT / "yandex_enrichment_experiment" / "data_750m" / "research_final"
BLOCK_TYPES = {"image", "media", "font"}
SOCIAL_NOBLOCK = {"vk.com", "instagram.com", "facebook.com", "ok.ru"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}
TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=20.0)


def host(url: str) -> str:
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def is_social(url: str) -> bool:
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in SOCIAL_NOBLOCK)


def _browser_proxy(tries=30):
    now = time.monotonic()
    fb = None
    for _ in range(tries):
        p = proxy_provider.get_proxy()
        if not p:
            return None, None
        u = _build_proxy_url(p)
        fb = (p, u)
        if _DEAD_PROXIES.get(u, 0.0) <= now:
            return p, u
    return fb if fb else (None, None)


async def fetch_httpx(url: str, tries=6) -> dict:
    target = rewrite_url(url)
    last = None
    for _ in range(tries):
        proxy = _httpx_proxy()
        try:
            async with httpx.AsyncClient(proxy=proxy, headers=HEADERS, timeout=TIMEOUT,
                                         follow_redirects=True) as c:
                r = await c.get(target)
            if r.status_code == 200 and len(r.text) >= 1500:
                txt = html_to_text(r.text)[:30000]
                return {"ok": True, "wire": r.num_bytes_downloaded, "words": count_words(txt), "method": "httpx"}
            last = f"status={r.status_code} len={len(r.text)}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:60]}"
            if any(s in last.lower() for s in ("connect", "timeout", "proxy", "tunnel", "reset")):
                _mark_proxy_dead(proxy)
    return {"ok": False, "wire": 0, "words": 0, "method": "httpx", "error": last}


async def fetch_browser(url: str, block: bool, tries=4) -> dict:
    ua = UserAgentPool().get_user_agent()
    last = None
    for _ in range(tries):
        proxy, purl = _browser_proxy()
        ctx = None
        try:
            ctx = await pool_manager.create_context(user_agent=ua, stealth=True, proxy=proxy,
                                                    locale="ru-RU", timezone_id="Europe/Moscow")
            wire = {"n": 0}
            pend = []
            if block:
                async def _route(route, req):
                    if req.resource_type in BLOCK_TYPES:
                        try: await route.abort()
                        except Exception: pass
                    else:
                        try: await route.continue_()
                        except Exception: pass
                await ctx.route("**/*", _route)
            page = await ctx.new_page()

            def on_fin(req):
                async def _add():
                    try:
                        s = await req.sizes()
                        wire["n"] += (s.get("responseBodySize", 0) or 0) + (s.get("responseHeadersSize", 0) or 0)
                    except Exception:
                        pass
                pend.append(asyncio.create_task(_add()))
            page.on("requestfinished", on_fin)

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.0)
            html = await page.content()
            if pend:
                await asyncio.gather(*pend, return_exceptions=True)
            txt = html_to_text(html)
            return {"ok": True, "wire": wire["n"], "words": count_words(txt),
                    "method": "browser" + ("+block" if block else "")}
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:60]}"
            if any(s in last.lower() for s in ("tunnel", "timeout", "proxy", "reset")):
                _mark_proxy_dead(purl)
        finally:
            if ctx is not None:
                try: await ctx.close()
                except Exception: pass
    return {"ok": False, "wire": 0, "words": 0, "method": "browser", "error": last}


async def old_path(url: str) -> dict:
    # pre-change: browser for everything, no resource-block.
    return await fetch_browser(url, block=False)


async def new_path(url: str) -> dict:
    # shipped routing.
    if is_instagram(url):
        h = instagram_handle(url)
        return {"ok": True, "wire": 0, "words": (2 if h else 0), "method": "ig_stub"}
    if host_in_allowlist(url):
        r = await fetch_httpx(url)
        if r["ok"]:
            return r
        # implementation falls back to browser on httpx failure
        return await fetch_browser(url, block=not is_social(url))
    return await fetch_browser(url, block=not is_social(url))


def pick_orgs(n=15, min_urls=4, max_urls=6):
    rows = []
    for f in sorted(DATA.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        trace = (d.get("result") or {}).get("trace_summary") or {}
        urls = [u for u in (trace.get("visited_urls") or []) if isinstance(u, str)]
        urls = [u for u in urls if host(u) not in ("t.me",)]
        # dedup, keep order, want domain variety
        seen, keep = set(), []
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            keep.append(u)
        if len(keep) >= min_urls:
            rows.append((d.get("oid"), d.get("title"), keep[:max_urls]))
    # spread across the file list for variety
    step = max(1, len(rows) // n)
    return rows[::step][:n]


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 15
    orgs = pick_orgs(n=n)
    print(f"A/B on {len(orgs)} orgs\n")
    results = []
    for oid, title, urls in orgs:
        org = {"oid": oid, "title": title, "urls": [], "old_bytes": 0, "new_bytes": 0,
               "old_words": 0, "new_words": 0}
        for url in urls:
            o = await old_path(url)
            n = await new_path(url)
            org["old_bytes"] += o["wire"]; org["new_bytes"] += n["wire"]
            org["old_words"] += o["words"]; org["new_words"] += n["words"]
            org["urls"].append({"url": url, "host": host(url),
                                "old": o, "new": n})
        ob, nb = org["old_bytes"], org["new_bytes"]
        factor = (ob / nb) if nb else float("inf")
        print(f"{str(oid):14} {str(title)[:22]:22} OLD={ob/1024/1024:6.2f}MB "
              f"NEW={nb/1024/1024:6.2f}MB  {factor:5.1f}x  "
              f"words old={org['old_words']:5} new={org['new_words']:5}")
        results.append(org)

    out = Path(__file__).resolve().parent / "ab_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    TOB = sum(r["old_bytes"] for r in results)
    TNB = sum(r["new_bytes"] for r in results)
    # Content retention is measured as PRESENCE per URL, not raw word count: the
    # OLD browser returns full untruncated page text while NEW httpx is capped at
    # 30k chars + the agent only ever consumes a 3.5k-char goal-extract, so raw
    # word ratios are an artifact. A "regression" = OLD had real content (>=40
    # words) on a URL but NEW did not.
    THRESH = 40
    urls_old = urls_retained = regressions = 0
    reg_list = []
    for r in results:
        for u in r["urls"]:
            ow, nw = u["old"]["words"], u["new"]["words"]
            # instagram stub legitimately yields ~no words but isn't a loss
            if u["new"].get("method") == "ig_stub":
                continue
            if ow >= THRESH:
                urls_old += 1
                if nw >= THRESH:
                    urls_retained += 1
                else:
                    regressions += 1
                    reg_list.append((r["oid"], u["host"], ow, nw, u["new"].get("method")))
    print("\n===== AGGREGATE =====")
    print(f"orgs={len(results)}")
    print(f"OLD total = {TOB/1024/1024:.1f} MB  ({TOB/1024/1024/len(results):.2f} MB/org)")
    print(f"NEW total = {TNB/1024/1024:.1f} MB  ({TNB/1024/1024/len(results):.2f} MB/org)")
    print(f"traffic reduction = {100*(1-TNB/TOB):.0f}%  ({TOB/TNB:.1f}x)")
    print(f"content retention = {urls_retained}/{urls_old} URLs kept content "
          f"({100*urls_retained/max(urls_old,1):.0f}%); regressions={regressions}")
    for oid, h, ow, nw, m in reg_list:
        print(f"   REGRESSION {oid} {h}: old={ow}w new={nw}w [{m}]")
    print(f"wrote {out}")
    await pool_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
