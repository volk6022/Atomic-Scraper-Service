"""
fl_httpx_test.py — Test plain httpx against fl.ru project listing pages.

Verifies:
  - Whether httpx can get real HTML or hits a DDoS-Guard / Cloudflare challenge
  - Server headers / anti-bot fingerprints
  - Whether content is server-rendered (projects visible in HTML) or JS-driven
  - Direct (no proxy) vs proxy comparison

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_httpx_test.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient, load_proxies  # noqa: E402

URLS = [
    ("projects_listing", "https://www.fl.ru/projects/"),
    ("projects_python", "https://www.fl.ru/projects/category/programmirovanie/python/"),
    ("projects_ai", "https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
    ("projects_programming", "https://www.fl.ru/projects/category/programmirovanie/"),
    ("robots_txt", "https://www.fl.ru/robots.txt"),
    # Try sort-by-date param guesses from robots.txt
    ("projects_listing_ord_date", "https://www.fl.ru/projects/?ord=date"),
    ("projects_listing_sort_date", "https://www.fl.ru/projects/?sort=date"),
    # Individual project card URL pattern
    ("project_card_sample", "https://www.fl.ru/projects/5500352/"),
]

REALISTIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


def detect_antibot(resp: httpx.Response) -> dict:
    """Check response headers and body for anti-bot fingerprints."""
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    body = resp.text[:3000]

    signals = {
        "server": hdrs.get("server", ""),
        "via": hdrs.get("via", ""),
        "cf_ray": hdrs.get("cf-ray", ""),
        "cf_cache_status": hdrs.get("cf-cache-status", ""),
        "x_ddos_guard": hdrs.get("x-ddos-guard", ""),
        "x_ddos_protection": hdrs.get("x-ddos-protection", ""),
        "__ddg1_": hdrs.get("__ddg1_", ""),
        "__ddg2_": hdrs.get("__ddg2_", ""),
        "set_cookie_ddg": any("__ddg" in c for c in resp.headers.get_list("set-cookie")),
        "set_cookie_cf": any("cf_clearance" in c for c in resp.headers.get_list("set-cookie")),
        "x_request_id": hdrs.get("x-request-id", ""),
    }

    # Body signals
    in_body = {
        "ddos_guard_in_body": "ddos-guard" in body.lower(),
        "cloudflare_in_body": "cloudflare" in body.lower(),
        "js_challenge_in_body": (
            "checking your browser" in body.lower() or
            "just a moment" in body.lower() or
            "please wait" in body.lower() or
            "enable javascript" in body.lower() or
            "turnstile" in body.lower()
        ),
        "project_list_in_body": (
            "b-post" in body.lower() or
            "project-item" in body.lower() or
            "fl-project" in body.lower() or
            "data-id" in body.lower() or
            "/projects/" in body
        ),
        "has_react_root": "__NEXT_DATA__" in body or "react-root" in body or "window.__" in body,
    }

    # Verdict
    if signals["cf_ray"]:
        verdict = "CLOUDFLARE"
    elif signals["x_ddos_guard"] or signals["set_cookie_ddg"] or in_body["ddos_guard_in_body"]:
        verdict = "DDOS-GUARD"
    elif in_body["js_challenge_in_body"]:
        verdict = "JS-CHALLENGE (unknown provider)"
    elif in_body["project_list_in_body"]:
        verdict = "REAL-CONTENT-SSR"
    else:
        verdict = "UNKNOWN"

    return {**signals, **in_body, "verdict": verdict}


def test_url_via_proxy(url: str, name: str, client: ProxyRotatingClient) -> dict:
    """Fetch a URL via rotating proxy and characterize the response."""
    print(f"\n  [proxy] GET {url}")
    try:
        resp = client.get(url)
        print(f"    Status: {resp.status_code}")
        ab = detect_antibot(resp)
        print(f"    Anti-bot verdict: {ab['verdict']}")
        print(f"    Server: {ab['server']}")
        print(f"    Content-Length: {len(resp.content)} bytes")
        (SAMPLES / f"fl_httpx_proxy_{name}.html").write_bytes(resp.content[:50000])

        # Try to extract project titles from HTML if real content
        titles = []
        if ab["project_list_in_body"] or resp.status_code == 200:
            import re
            # Various patterns for project titles in listings
            patterns = [
                r'class="[^"]*title[^"]*"[^>]*>([^<]{10,100})',
                r'"projectName"\s*:\s*"([^"]{5,100})"',
                r'data-project-title="([^"]{5,100})"',
            ]
            body = resp.text
            for pat in patterns:
                found = re.findall(pat, body)[:3]
                if found:
                    titles.extend(found)
                    break

        return {
            "via": "proxy",
            "status": resp.status_code,
            "content_length": len(resp.content),
            "anti_bot": ab,
            "sample_titles": titles[:3],
            "body_snippet": resp.text[:800],
        }
    except Exception as e:
        print(f"    FAILED: {e}")
        return {"via": "proxy", "error": str(e)}


def test_url_direct(url: str, name: str) -> dict:
    """Fetch a URL WITHOUT proxy (direct connection) for comparison."""
    print(f"\n  [direct] GET {url}")
    try:
        with httpx.Client(
            timeout=15.0,
            headers=REALISTIC_HEADERS,
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            print(f"    Status: {resp.status_code}")
            ab = detect_antibot(resp)
            print(f"    Anti-bot verdict: {ab['verdict']}")
            (SAMPLES / f"fl_httpx_direct_{name}.html").write_bytes(resp.content[:50000])
            return {
                "via": "direct",
                "status": resp.status_code,
                "content_length": len(resp.content),
                "anti_bot": ab,
                "body_snippet": resp.text[:400],
            }
    except Exception as e:
        print(f"    FAILED: {e}")
        return {"via": "direct", "error": str(e)}


def main():
    client = ProxyRotatingClient(max_retries=15, timeout=30.0)
    results = {}

    print("=" * 60)
    print("FL.RU HTTPX VERIFICATION")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Test a subset via both direct and proxy
    priority_urls = [
        ("projects_listing", "https://www.fl.ru/projects/"),
        ("projects_python", "https://www.fl.ru/projects/category/programmirovanie/python/"),
        ("robots_txt", "https://www.fl.ru/robots.txt"),
    ]

    for name, url in priority_urls:
        print(f"\n{'='*50}")
        print(f"URL: {url}")
        direct_result = test_url_direct(url, name)
        proxy_result = test_url_via_proxy(url, name, client)
        results[name] = {
            "url": url,
            "direct": direct_result,
            "proxy": proxy_result,
        }

    # Test remaining via proxy only
    remaining_urls = [u for u in URLS if u[0] not in {n for n, _ in priority_urls}]
    for name, url in remaining_urls:
        print(f"\n{'='*50}")
        print(f"URL: {url}")
        results[name] = {
            "url": url,
            "proxy": test_url_via_proxy(url, name, client),
        }

    # Save results
    summary_path = SAMPLES / "fl_httpx_results.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\nResults saved to: {summary_path}")

    print("\n=== SUMMARY ===")
    for name, r in results.items():
        proxy_r = r.get("proxy", {})
        direct_r = r.get("direct", {})
        proxy_verdict = proxy_r.get("anti_bot", {}).get("verdict", proxy_r.get("error", "N/A"))
        direct_verdict = direct_r.get("anti_bot", {}).get("verdict", direct_r.get("error", "N/A"))
        if direct_r:
            print(f"  {name}: direct={direct_verdict} | proxy={proxy_verdict}")
        else:
            print(f"  {name}: proxy={proxy_verdict}")


if __name__ == "__main__":
    main()
