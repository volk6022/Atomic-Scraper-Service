# -*- coding: utf-8 -*-
"""
fl_fetch_json_apis.py - Fetch and decode the discovered fl.ru JSON API endpoints.

Also tries to trigger the infinite scroll "load more" endpoint by:
1. Fetching the page to get a CSRF token and session cookies
2. Making XHR calls with those headers to /projects/ variants

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_fetch_json_apis.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient, FL_HEADERS, FL_HEADERS_JSON  # noqa: E402

import httpx


def get_csrf_and_cookies(client: ProxyRotatingClient) -> tuple[str, dict]:
    """Fetch the projects page to get CSRF token + DDoS-Guard cookies."""
    resp = client.get("https://www.fl.ru/projects/")
    body = resp.text

    # Extract CSRF token from meta tag
    csrf_match = re.search(r'meta[^>]+name="csrf-token"[^>]+content="([^"]+)"', body)
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # Build cookie dict from set-cookie headers
    cookies = {}
    for c in resp.headers.get_list("set-cookie"):
        # Parse name=value
        parts = c.split(";")[0].strip()
        if "=" in parts:
            k, v = parts.split("=", 1)
            cookies[k.strip()] = v.strip()

    # Also add PHPSESSID from response if present
    phpsessid_match = re.search(r"PHPSESSID=([^;]+)", c if cookies else "")

    print(f"  CSRF token: {csrf_token[:30]}...")
    print(f"  Cookies set: {list(cookies.keys())}")
    return csrf_token, cookies


def build_xhr_headers(csrf_token: str, cookies: dict, referer: str = "https://www.fl.ru/projects/") -> dict:
    """Build headers that mimic a browser XHR request."""
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": csrf_token,
        "X-XSRF-TOKEN": csrf_token,
        "Cookie": cookie_str,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.fl.ru",
    }


def main():
    client = ProxyRotatingClient(max_retries=10, timeout=25.0)
    results = {}

    print("=== Fetching CSRF token and cookies ===")
    try:
        csrf_token, cookies = get_csrf_and_cookies(client)
    except Exception as e:
        print(f"  FAILED: {e}")
        csrf_token = ""
        cookies = {}

    xhr_headers = build_xhr_headers(csrf_token, cookies)

    # ---- Known JSON endpoints ----
    json_endpoints = [
        ("prof_groups", "GET", "https://www.fl.ru/prof_groups/", None),
        ("countries", "GET", "https://www.fl.ru/countries/", None),
        ("session_filter", "GET", "https://www.fl.ru/projects/session/filter/", None),
    ]

    # ---- Try to find the "load more" / infinite scroll endpoint ----
    # Based on xajax pattern found in HTML - try xajax endpoint
    # Also try common REST patterns
    load_more_candidates = [
        ("xajax_post", "POST", "https://www.fl.ru/xajax", {
            "xajax": "GetProjectList",
            "xajaxargs[]": json.dumps({"page": 2, "category": "", "sort": "date"})
        }),
        ("projects_list_page2", "GET", "https://www.fl.ru/projects/?page=2", None),
        ("projects_list_more", "GET", "https://www.fl.ru/projects/?offset=30", None),
        ("projects_ajax", "GET", "https://www.fl.ru/projects/ajax/", None),
        ("projects_feed", "GET", "https://www.fl.ru/projects/feed/", None),
        ("projects_json", "GET", "https://www.fl.ru/projects/?format=json", None),
    ]

    all_endpoints = json_endpoints + load_more_candidates

    print("\n=== Fetching JSON API endpoints ===")
    for name, method, url, post_data in all_endpoints:
        print(f"\n  [{method}] {url}")
        try:
            if method == "GET":
                resp = client.request("GET", url, headers=xhr_headers)
            else:
                resp = client.request("POST", url, headers={**xhr_headers, "Content-Type": "application/x-www-form-urlencoded"},
                                     data=urllib.parse.urlencode(post_data) if post_data else None)

            status = resp.status_code
            ct = resp.headers.get("content-type", "")
            print(f"    Status: {status}  CT: {ct}")

            if "json" in ct or status == 200 and resp.text.lstrip().startswith(("{", "[")):
                try:
                    data = resp.json()
                    snippet = json.dumps(data, ensure_ascii=False)[:800]
                    print(f"    JSON: {snippet}")
                    (SAMPLES / f"fl_api_{name}.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    results[name] = {"status": status, "json": data if len(str(data)) < 5000 else "LARGE"}
                except Exception as e:
                    print(f"    JSON parse error: {e}")
                    print(f"    Body: {resp.text[:400]}")
                    results[name] = {"status": status, "error": str(e), "body": resp.text[:400]}
            else:
                body_snippet = resp.text[:400]
                print(f"    Not JSON — body: {body_snippet[:200]}")
                (SAMPLES / f"fl_api_{name}.html").write_text(resp.text[:50000], encoding="utf-8")
                results[name] = {"status": status, "not_json": True, "body": body_snippet}
        except Exception as e:
            print(f"    ERROR: {e}")
            results[name] = {"error": str(e)}

    # Save all results
    out = SAMPLES / "fl_json_api_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out}")

    print("\n=== SUMMARY ===")
    for name, r in results.items():
        if "error" in r:
            print(f"  {name}: ERROR — {r['error']}")
        elif r.get("not_json"):
            print(f"  {name}: HTTP {r['status']} — not JSON (HTML/challenge)")
        else:
            keys = list(r.get("json", {}).keys()) if isinstance(r.get("json"), dict) else "array"
            print(f"  {name}: HTTP {r['status']} — JSON OK, keys={keys}")


if __name__ == "__main__":
    main()
