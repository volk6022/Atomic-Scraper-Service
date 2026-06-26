"""
kwork_probe_xhr.py — Deep probe of POST https://kwork.ru/projects anonymous JSON endpoint.

Found in kwork_analyze_html.py: POST /projects returns JSON with wants data.
This script:
  1. Captures full response schema
  2. Tests category filters (cat_id, catId, category_id, etc.)
  3. Tests page parameter
  4. Tests price range parameters
  5. Finds category IDs for Python/ML/AI
  6. Maps the WantWorker field schema from live response

Run from repo root:
  uv run python experiment-kwork/kwork_probe_xhr.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES_DIR = Path(__file__).parent / "samples" / "xhr"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://kwork.ru/projects",
    "Origin": "https://kwork.ru",
}

XHR_URL = "https://kwork.ru/projects"


def post_projects(params: dict) -> dict:
    """POST to /projects with form data. Returns parsed JSON."""
    with httpx.Client(headers=BASE_HEADERS, follow_redirects=True, timeout=20.0) as c:
        r = c.post(XHR_URL, data=params)
    r.raise_for_status()
    return r.json()


def safe_post(params: dict, label: str) -> dict | None:
    print(f"\n[POST /projects] {label}")
    print(f"  params={params}")
    try:
        data = post_projects(params)
        success = data.get("success", False)
        d = data.get("data", {})
        print(f"  success={success}")
        # Find the wants list — key has format wants_{category_id}_data
        wants_keys = [k for k in d.keys() if "wants" in k and k.endswith("_data")]
        print(f"  wants_keys={wants_keys}")
        for wk in wants_keys:
            items = d[wk]
            print(f"  {wk}: {len(items)} items")
            if items:
                first = items[0]
                print(f"    first item keys: {list(first.keys())[:20]}")
                print(f"    want_id={first.get('id', first.get('want_id', '?'))}")
                print(f"    name={first.get('name', '')[:80]!r}")
                print(f"    price={first.get('price', first.get('price_from', '?'))}")
                print(f"    category_id={first.get('category_id', first.get('cat_id', '?'))}")
        # Pagination
        pagination = d.get("pagination", {})
        if pagination:
            print(f"  pagination: current={pagination.get('current_page')} data_count={len(pagination.get('data',[]))}")
        return data
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return None


if __name__ == "__main__":
    # 1. Baseline — no filters
    r_base = safe_post({}, "baseline (no filters)")
    if r_base:
        (SAMPLES_DIR / "base_response.json").write_text(
            json.dumps(r_base, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 2. Try category filter variations — need to find param name
    # From the HTML we see category IDs like 79 (ML), 35, etc.
    # Try common param names
    cat_param_candidates = [
        {"c": "79"},
        {"cat": "79"},
        {"cat_id": "79"},
        {"catId": "79"},
        {"category_id": "79"},
        {"categories_ids[]": "79"},
        {"categories[]": "79"},
        {"category": "79"},
    ]
    for p in cat_param_candidates:
        r = safe_post(p, f"category filter: {p}")
        if r:
            d = r.get("data", {})
            wants_keys = [k for k in d.keys() if "wants" in k and k.endswith("_data")]
            total = sum(len(d[k]) for k in wants_keys)
            if total > 0:
                print(f"  *** FOUND WORKING CATEGORY PARAM: {list(p.keys())[0]}={list(p.values())[0]}")
                print(f"  *** Returns {total} projects")
                (SAMPLES_DIR / f"category_filter_{list(p.keys())[0]}.json").write_text(
                    json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    # 3. Try c=79 (most likely based on URL patterns seen)
    print("\n--- Detailed category 79 probe ---")
    r79 = safe_post({"c": "79"}, "c=79 (ML/AI)")
    if r79:
        (SAMPLES_DIR / "category_79.json").write_text(
            json.dumps(r79, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 4. Try c=11 (Python)
    print("\n--- Detailed category 11 probe ---")
    r11 = safe_post({"c": "11"}, "c=11 (Python dev)")
    if r11:
        (SAMPLES_DIR / "category_11.json").write_text(
            json.dumps(r11, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 5. Try c=all or no c to get all
    r_all = safe_post({"c": "all"}, "c=all")
    if r_all:
        (SAMPLES_DIR / "category_all.json").write_text(
            json.dumps(r_all, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 6. Page parameter
    r_p2 = safe_post({"page": "2"}, "page=2")
    if r_p2:
        d_p2 = r_p2.get("data", {})
        wants_keys = [k for k in d_p2.keys() if "wants" in k and k.endswith("_data")]
        first_page_ids = set()
        if r_base:
            for k in r_base.get("data", {}).keys():
                if "wants" in k and k.endswith("_data"):
                    for item in r_base["data"][k]:
                        first_page_ids.add(item.get("id", item.get("want_id", "")))
        page2_ids = set()
        for k in wants_keys:
            for item in d_p2[k]:
                page2_ids.add(item.get("id", item.get("want_id", "")))
        print(f"  page1_ids_sample={list(first_page_ids)[:5]}")
        print(f"  page2_ids_sample={list(page2_ids)[:5]}")
        print(f"  different_pages={bool(page2_ids - first_page_ids)}")

    # 7. Price filter
    safe_post({"price_from": "5000", "price_to": "50000"}, "price filter 5k-50k")

    # 8. Get full schema from base response first item
    print("\n--- Full schema of first WantWorker object ---")
    if r_base:
        d = r_base.get("data", {})
        for k in d.keys():
            if "wants" in k and k.endswith("_data") and d[k]:
                first = d[k][0]
                print(json.dumps(first, ensure_ascii=False, indent=2))
                (SAMPLES_DIR / "want_worker_schema.json").write_text(
                    json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                break

    # 9. Look for category list endpoint
    print("\n--- Category list endpoint probes ---")
    cat_endpoint_candidates = [
        "https://kwork.ru/api/categories",
        "https://kwork.ru/api/projects/categories",
        "https://kwork.ru/projects/categories",
        "https://kwork.ru/api/want/categories",
    ]
    for url in cat_endpoint_candidates:
        try:
            with httpx.Client(headers={
                **BASE_HEADERS,
                "Content-Type": "application/json",
            }, follow_redirects=True, timeout=10.0) as c:
                r = c.get(url)
            snippet = r.text[:200]
            print(f"  GET {url} -> {r.status_code} snippet={snippet[:80]!r}")
        except Exception as exc:
            print(f"  GET {url} -> ERROR: {exc}")

    print("\nDone. Evidence in:", SAMPLES_DIR)
