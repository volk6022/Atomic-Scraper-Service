# -*- coding: utf-8 -*-
"""
fl_analyze_html.py - Analyze the fl.ru projects listing HTML structure.

Fetches the Python and AI category pages, extracts:
- Project IDs
- Budget visibility (anonymous)
- Sort/ord URL params
- XHR API endpoints embedded in JS
- Pagination mechanism

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_analyze_html.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient  # noqa: E402

URLS_TO_ANALYZE = [
    ("projects_all", "https://www.fl.ru/projects/"),
    ("projects_python", "https://www.fl.ru/projects/category/programmirovanie/python/"),
    ("projects_ai", "https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"),
    # Sort param guesses from robots.txt
    ("projects_ord_date", "https://www.fl.ru/projects/?ord=date"),
    ("projects_ord_desc", "https://www.fl.ru/projects/?ord=desc"),
    # Try ?order= and ?sort=
    ("projects_order_date", "https://www.fl.ru/projects/?order=date"),
    ("projects_sort_date", "https://www.fl.ru/projects/?sort=date"),
    # Try proonly.php
    ("proonly", "https://www.fl.ru/proonly.php"),
]


def analyze_page(body: str, url: str) -> dict:
    """Extract structured info from a page's HTML."""
    results = {}

    # Project IDs
    ids = re.findall(r"/projects/(\d{5,8})/", body)
    ids_unique = list(dict.fromkeys(ids))[:20]
    results["project_ids"] = ids_unique
    results["project_count"] = len(ids_unique)

    # Budget visibility
    budget_patterns = [
        r"(\d[\d\s]{1,9}\s*&#8381;)",  # numeric + RUB symbol
        r"(\d[\d\s]{1,9}\s*руб)",       # Russian 'rubles'
        r"Бюджет[^<]{1,50}",            # 'Budget:' prefix
    ]
    budgets = []
    for pat in budget_patterns:
        found = re.findall(pat, body)[:5]
        budgets.extend(found)
    results["budget_visible"] = budgets[:8]

    # XHR/API endpoints in JS
    api_patterns = [
        r'["\'](/api/[^"\'<>\s]{3,80})["\']',
        r'url\s*:\s*["\']([^"\']{5,80})["\']',
        r'fetch\s*\(\s*["\']([^"\']{5,80})["\']',
        r'axios\.[a-z]+\s*\(\s*["\']([^"\']{5,80})["\']',
    ]
    api_urls = []
    for pat in api_patterns:
        found = re.findall(pat, body)[:10]
        api_urls.extend([u for u in found if "/api/" in u or "ajax" in u.lower()])
    results["api_urls_in_js"] = list(dict.fromkeys(api_urls))[:15]

    # Sort params in pagination links
    sort_in_links = re.findall(r'href="[^"]*[?&](ord|sort|order)=([^"&]{1,30})[^"]*"', body)[:10]
    results["sort_params_in_links"] = sort_in_links

    # Any ?ord= or ?sort= in the page
    ord_values = re.findall(r"[?&]ord=([^&\"'\s<>]{1,30})", body)[:10]
    sort_values = re.findall(r"[?&]sort=([^&\"'\s<>]{1,30})", body)[:10]
    results["ord_values_found"] = list(dict.fromkeys(ord_values))
    results["sort_values_found"] = list(dict.fromkeys(sort_values))

    # Pagination links
    page_links = re.findall(r'href="[^"]*\?page=(\d+)[^"]*"', body)[:5]
    page_links2 = re.findall(r'href="[^"]*?/(\d+)/?[^"]*".*?class="[^"]*pag', body)[:3]
    results["pagination_page_params"] = page_links
    results["pagination_total_pages_found"] = len(page_links)

    # JavaScript window vars
    js_window_vars = re.findall(r"window\.__([A-Z_]+)\s*=\s*({[^;]{10,200})", body)[:5]
    results["js_window_vars"] = [(k, v[:100]) for k, v in js_window_vars]

    # Check for CSRF in meta
    csrf_meta = re.findall(r'meta[^>]+name="csrf-token"[^>]+content="([^"]+)"', body)
    results["csrf_token_present"] = bool(csrf_meta)
    if csrf_meta:
        results["csrf_token_sample"] = csrf_meta[0][:20] + "..."

    # Check for token key meta
    token_key = re.findall(r'meta[^>]+name="_TOKEN_KEY"[^>]+content="([^"]+)"', body)
    results["token_key_present"] = bool(token_key)
    if token_key:
        results["token_key_sample"] = token_key[0][:20] + "..."

    # current-uid (0 = anonymous)
    uid = re.findall(r'name="current-uid"[^>]+content="([^"]+)"', body)
    results["current_uid"] = uid[0] if uid else "not_found"

    # b-post class (old FL.ru project listing CSS class)
    b_post_count = body.count("b-post")
    results["b_post_count"] = b_post_count

    return results


def main():
    client = ProxyRotatingClient(max_retries=10, timeout=30.0)
    all_results = {}

    for name, url in URLS_TO_ANALYZE:
        print(f"\nGET {url}")
        try:
            resp = client.get(url)
            status = resp.status_code
            body = resp.text
            print(f"  Status: {status}  Server: {resp.headers.get('server', '')}  Len: {len(body)}")

            # Save full HTML
            save_path = SAMPLES / f"fl_analyze_{name}.html"
            save_path.write_bytes(resp.content[:300000])

            if status == 200:
                analysis = analyze_page(body, url)
                print(f"  Projects found: {analysis['project_count']}")
                print(f"  Budgets visible: {analysis['budget_visible'][:3]}")
                print(f"  API URLs: {analysis['api_urls_in_js'][:3]}")
                print(f"  Sort params in links: {analysis['sort_params_in_links'][:3]}")
                print(f"  Ord values: {analysis['ord_values_found']}")
                print(f"  b-post count: {analysis['b_post_count']}")
                print(f"  CSRF present: {analysis['csrf_token_present']}")
                print(f"  current-uid: {analysis['current_uid']}")
                all_results[name] = {"url": url, "status": status, **analysis}
            else:
                body_snippet = body[:400]
                print(f"  Body snippet: {body_snippet}")
                all_results[name] = {"url": url, "status": status, "body_snippet": body_snippet}
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results[name] = {"url": url, "error": str(e)}

    # Save results
    out = SAMPLES / "fl_analyze_results.json"
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out}")

    # Summary
    print("\n=== FINAL SUMMARY ===")
    for name, r in all_results.items():
        if "error" in r:
            print(f"  {name}: ERROR")
        else:
            print(f"  {name}: HTTP {r['status']} | projects={r.get('project_count',0)} "
                  f"| budgets={len(r.get('budget_visible',[]))} "
                  f"| api={len(r.get('api_urls_in_js',[]))} "
                  f"| b-post={r.get('b_post_count',0)}")


if __name__ == "__main__":
    main()
