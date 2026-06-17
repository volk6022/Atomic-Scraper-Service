"""Shared harness for per-site scale tests.

Each site script defines its 20 URLs + a content validator and calls `run_site`.
We send N requests (default 100) cycling the URL list, through the rotating
residential proxy pool, and measure:
  - request stability: HTTP-200-with-body success rate
  - content stability: fraction where the site-specific validator found real data
  - traffic at scale: total wire bytes (num_bytes_downloaded) + per-request stats

httpx is told `Accept-Encoding: gzip, deflate` (NO brotli) — the venv lacks the
brotli lib and `br` responses decode to garbage (see ../FINDINGS.md).
"""
from __future__ import annotations

import asyncio
import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

PHONE_RE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


def has_phone(html: str) -> bool:
    return bool(PHONE_RE.search(html))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.actions.yandex_maps import _httpx_proxy, _mark_proxy_dead  # noqa: E402
from src.infrastructure.browser.proxy_provider import proxy_provider  # noqa: E402

# The module-level proxy_provider loads "proxies.txt" relative to CWD; these
# scripts may run from any dir, so force-load the repo-root file. Without this
# the pool is empty -> requests go direct -> Russian sites time out.
if not getattr(proxy_provider, "_proxies", None):
    proxy_provider.proxy_file = ROOT / "proxies.txt"
    proxy_provider._load_proxies()
if not proxy_provider._proxies:
    raise SystemExit(f"no proxies loaded from {ROOT / 'proxies.txt'}")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate",  # NO brotli — see module docstring
}
TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=20.0)

URLS_JSON = Path(__file__).resolve().parent / "urls.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_urls(site: str) -> list[str]:
    data = json.loads(URLS_JSON.read_text(encoding="utf-8"))
    urls = data.get(site) or []
    if not urls:
        raise SystemExit(f"no URLs for site={site} in {URLS_JSON}")
    return urls


async def _one_request(
    url: str, rewrite: Callable[[str], str], validate: Callable[[str], dict],
    sem: asyncio.Semaphore, proxy_tries: int = 6,
) -> dict:
    """One logical request (may rotate through several proxies). Bytes are summed
    across all proxy attempts (realistic traffic). `validate(html)` -> signals dict
    that MUST contain bool key 'content_ok'."""
    target = rewrite(url)
    rec = {"url": url, "fetched": target if target != url else None,
           "wire_bytes": 0, "attempts": 0, "ok": False, "content_ok": False,
           "status": None, "latency_s": None, "error": None}
    t0 = time.time()
    async with sem:
        last = None
        for _ in range(proxy_tries):
            proxy = _httpx_proxy()
            rec["attempts"] += 1
            try:
                async with httpx.AsyncClient(
                    proxy=proxy, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
                ) as c:
                    resp = await c.get(target)
                    rec["wire_bytes"] += resp.num_bytes_downloaded
                    rec["status"] = resp.status_code
                    html = resp.text
                    if resp.status_code == 200 and len(html) > 800:
                        rec["ok"] = True
                        sig = validate(html)
                        rec["content_ok"] = bool(sig.get("content_ok"))
                        rec["signals"] = {k: v for k, v in sig.items() if k != "content_ok"}
                        break
                    last = f"status={resp.status_code} len={len(html)}"
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:80]}"
                if any(s in last.lower() for s in ("connect", "timeout", "proxy", "tunnel", "reset")):
                    _mark_proxy_dead(proxy)
        if not rec["ok"]:
            rec["error"] = last
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec


async def run_site(
    site: str, rewrite: Callable[[str], str], validate: Callable[[str], dict],
    n_requests: int = 100, concurrency: int = 6,
) -> dict:
    # CLI override: `python site_x.py [n_requests] [concurrency]` (handy for smoke tests)
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        n_requests = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        concurrency = int(sys.argv[2])
    urls = load_urls(site)
    plan = [urls[i % len(urls)] for i in range(n_requests)]
    sem = asyncio.Semaphore(concurrency)
    print(f"[{site}] {n_requests} requests over {len(urls)} unique URLs, "
          f"concurrency={concurrency} ...")
    t0 = time.time()
    recs = await asyncio.gather(*[_one_request(u, rewrite, validate, sem) for u in plan])
    elapsed = time.time() - t0

    ok = [r for r in recs if r["ok"]]
    content = [r for r in recs if r["content_ok"]]
    by_bytes = [r["wire_bytes"] for r in recs if r["wire_bytes"] > 0]
    ok_bytes = [r["wire_bytes"] for r in ok if r["wire_bytes"] > 0]
    statuses: dict = {}
    for r in recs:
        statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1

    def pct(xs, p):
        if not xs:
            return 0
        s = sorted(xs)
        return s[min(len(s) - 1, int(len(s) * p / 100))]

    summary = {
        "site": site,
        "n_requests": n_requests,
        "unique_urls": len(urls),
        "request_success_rate": round(len(ok) / n_requests, 3),
        "content_success_rate": round(len(content) / n_requests, 3),
        "total_wire_bytes": sum(by_bytes),
        "total_wire_mb": round(sum(by_bytes) / 1024 / 1024, 2),
        "avg_bytes_per_ok": int(statistics.mean(ok_bytes)) if ok_bytes else 0,
        "p50_bytes_ok": pct(ok_bytes, 50),
        "p95_bytes_ok": pct(ok_bytes, 95),
        "avg_attempts": round(statistics.mean([r["attempts"] for r in recs]), 2),
        "avg_latency_s": round(statistics.mean([r["latency_s"] for r in recs]), 2),
        "status_dist": statuses,
        "elapsed_s": round(elapsed, 1),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{site.replace('.', '_')}.json").write_text(
        json.dumps({"summary": summary, "records": recs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
