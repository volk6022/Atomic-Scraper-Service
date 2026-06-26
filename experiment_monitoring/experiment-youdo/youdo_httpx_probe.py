"""
youdo_httpx_probe.py — httpx-based probe for youdo.com task listings.

Attempt order:
  1. Direct httpx (no proxy) — check HTTP status, body snippet, anti-bot headers
  2. httpx with rotating proxy pool
  3. Try common XHR/JSON endpoint patterns (youdo has a React SPA, may have /api/ calls)
  4. Check robots.txt and sitemap for structure hints
  5. Check for GEO-block (RU-only content check)

Run from repo root:
  cd "C:\\Users\\bhunp\\Documents\\auto-monitor-ml-cv\\repos\\Atomic-Scraper-Service"
  uv run python experiment_monitoring\\experiment-youdo\\youdo_httpx_probe.py
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
EXPERIMENT_DIR = Path(__file__).parent
SAMPLES_DIR = EXPERIMENT_DIR / "samples" / "httpx"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
PROXIES_FILE = EXPERIMENT_DIR.parent.parent / "proxies.txt"  # repo root

# ---------------------------------------------------------------------------
# Proxy loading (reuse pattern from proxy_client.py)
# ---------------------------------------------------------------------------

import re
import random
import urllib.parse

_LINE_RE = re.compile(
    r"^https?://"
    r"(?P<user>[^:@]+)"
    r":"
    r"(?P<password>[^@]+)"
    r"@"
    r"(?P<host>[^:]+)"
    r":"
    r"(?P<port>\d+)$"
)


def load_proxies() -> list[str]:
    if not PROXIES_FILE.exists():
        print(f"[!] proxies.txt not found at {PROXIES_FILE}")
        return []
    proxies = []
    for raw in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            enc_user = urllib.parse.quote(m.group("user"), safe="")
            enc_pass = urllib.parse.quote(m.group("password"), safe="")
            proxies.append(f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}")
    random.shuffle(proxies)
    return proxies


PROXIES = load_proxies()
print(f"[*] Loaded {len(PROXIES)} proxies")

# ---------------------------------------------------------------------------
# Headers — mimic a real browser
# ---------------------------------------------------------------------------

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

XHR_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://youdo.com/tasks-all-opened-all",
    "Origin": "https://youdo.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# ---------------------------------------------------------------------------
# Probe helper
# ---------------------------------------------------------------------------

def probe(url: str, headers: dict, proxy: str | None = None, method: str = "GET",
          data: dict | None = None, label: str = "") -> dict:
    """Single request probe. Returns result dict."""
    result = {
        "url": url, "label": label, "proxy": proxy.split("@")[-1] if proxy else "direct",
        "status": None, "content_type": None, "body_len": 0,
        "body_snippet": "", "is_json": False, "json_keys": [],
        "anti_bot_headers": {}, "error": None,
    }
    kwargs: dict = {
        "headers": headers,
        "follow_redirects": True,
        "timeout": 25.0,
    }
    if proxy:
        kwargs["proxy"] = proxy
    try:
        with httpx.Client(**kwargs) as client:
            if method == "POST":
                resp = client.post(url, data=data or {})
            else:
                resp = client.get(url)
        result["status"] = resp.status_code
        result["content_type"] = resp.headers.get("content-type", "")
        result["body_len"] = len(resp.content)

        # Check anti-bot headers
        ab = {}
        for h in ["cf-ray", "cf-cache-status", "x-qrator-request-id", "x-qrator-ua",
                  "x-protected-by", "x-ddos-guard", "server"]:
            v = resp.headers.get(h)
            if v:
                ab[h] = v
        result["anti_bot_headers"] = ab

        # Body analysis
        try:
            text = resp.text
        except Exception:
            text = resp.content.decode("utf-8", errors="replace")
        result["body_snippet"] = text[:1500]

        # JSON detection
        ct = result["content_type"].lower()
        if "json" in ct or text.strip().startswith("{") or text.strip().startswith("["):
            try:
                parsed = resp.json()
                result["is_json"] = True
                if isinstance(parsed, dict):
                    result["json_keys"] = list(parsed.keys())[:20]
                elif isinstance(parsed, list):
                    result["json_keys"] = [f"list[{len(parsed)}]"]
            except Exception:
                pass

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def print_result(r: dict) -> None:
    status = r.get("status")
    ab = r.get("anti_bot_headers", {})
    ab_str = ", ".join(f"{k}={v[:30]}" for k, v in ab.items()) if ab else "none"
    print(f"  [{r['label']}] {r['proxy']} -> HTTP {status} | ct={r.get('content_type','')[:40]} | len={r.get('body_len',0)}")
    print(f"    anti-bot: {ab_str}")
    if r.get("error"):
        print(f"    ERROR: {r['error']}")
    if r.get("is_json"):
        print(f"    JSON keys: {r.get('json_keys')}")
    snippet = r.get("body_snippet", "")
    if snippet:
        print(f"    snippet: {snippet[:200]!r}")


# ---------------------------------------------------------------------------
# Target URLs
# ---------------------------------------------------------------------------

TARGETS = [
    # Main listings
    ("https://youdo.com/tasks-all-opened-all", "main_tasks_all", BROWSER_HEADERS),
    ("https://youdo.com/tasks-all", "main_tasks_all_short", BROWSER_HEADERS),
    # Freelance subdomain
    ("https://freelance.youdo.com/", "freelance_home", BROWSER_HEADERS),
    # Robots + sitemap
    ("https://youdo.com/robots.txt", "robots_txt", BROWSER_HEADERS),
    ("https://youdo.com/sitemap.xml", "sitemap_xml", BROWSER_HEADERS),
    # XHR/API guesses based on typical React SPA patterns
    ("https://youdo.com/api/v1/tasks", "api_v1_tasks", XHR_HEADERS),
    ("https://youdo.com/api/tasks", "api_tasks", XHR_HEADERS),
    ("https://youdo.com/api/v2/tasks", "api_v2_tasks", XHR_HEADERS),
    ("https://youdo.com/webapi/v1/tasks", "webapi_v1_tasks", XHR_HEADERS),
    ("https://youdo.com/api/tasks/list", "api_tasks_list", XHR_HEADERS),
    # Known YouDo URL patterns from search results
    ("https://youdo.com/api/v1/tasks/?page=1&status=opened", "api_tasks_opened_p1", XHR_HEADERS),
    ("https://youdo.com/api/v1/tasks?page=1&limit=20", "api_tasks_paged", XHR_HEADERS),
    ("https://youdo.com/api/v1/tasks/search", "api_tasks_search", XHR_HEADERS),
    # GraphQL guess
    ("https://youdo.com/graphql", "graphql", XHR_HEADERS),
    # Category-filtered
    ("https://youdo.com/tasks-all-opened-all?category=it", "tasks_cat_it", BROWSER_HEADERS),
]

# Candidate XHR POST endpoints (kwork pattern)
XHR_POST_CANDIDATES = [
    ("https://youdo.com/tasks-all-opened-all", {}),
    ("https://youdo.com/api/v1/tasks", {"page": "1", "status": "opened"}),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    evidence = {}

    print("\n=== PHASE 1: Direct httpx (no proxy) ===")
    for url, label, hdrs in TARGETS:
        r = probe(url, hdrs, proxy=None, label=f"direct/{label}")
        print_result(r)
        evidence[label] = r
        # Save bodies that are interesting
        if r["status"] and r["status"] < 400 and r["body_len"] > 500:
            fname = SAMPLES_DIR / f"{label}_direct.txt"
            fname.write_text(r["body_snippet"], encoding="utf-8")
            print(f"    [saved] {fname.name}")
        time.sleep(0.3)

    print("\n=== PHASE 2: httpx with proxy rotation ===")
    for url, label, hdrs in TARGETS[:5]:  # Only main URLs
        if not PROXIES:
            print("  No proxies available, skipping")
            break
        for attempt, proxy in enumerate(PROXIES[:5]):
            r = probe(url, hdrs, proxy=proxy, label=f"proxy{attempt+1}/{label}")
            print_result(r)
            key = f"{label}_proxy{attempt+1}"
            evidence[key] = r
            if r["status"] and r["status"] < 400 and r["body_len"] > 500:
                fname = SAMPLES_DIR / f"{label}_proxy{attempt+1}.txt"
                fname.write_text(r["body_snippet"], encoding="utf-8")
                print(f"    [saved] {fname.name}")
                break  # Got a good response, move on
            if not r.get("error") and r["status"] not in (None,):
                break  # Got any HTTP response (even 403), no need to keep rotating for same URL
            time.sleep(0.5)

    print("\n=== PHASE 3: XHR POST probes ===")
    for url, data in XHR_POST_CANDIDATES:
        r = probe(url, XHR_HEADERS, proxy=PROXIES[0] if PROXIES else None,
                  method="POST", data=data, label=f"post/{url.split('/')[-1]}")
        print_result(r)
        evidence[f"post_{url.split('/')[-1]}"] = r
        time.sleep(0.3)

    # Save full evidence
    evidence_path = SAMPLES_DIR / "httpx_evidence.json"
    try:
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        print(f"\n[*] Full evidence saved: {evidence_path}")
    except Exception as e:
        print(f"[!] Could not save evidence JSON: {e}")

    # Summary
    print("\n=== SUMMARY ===")
    for k, v in evidence.items():
        s = v.get("status")
        ab = list(v.get("anti_bot_headers", {}).keys())
        err = v.get("error", "")
        print(f"  {k}: HTTP {s} | anti-bot={ab} | json={v.get('is_json')} | err={err[:60] if err else '-'}")
