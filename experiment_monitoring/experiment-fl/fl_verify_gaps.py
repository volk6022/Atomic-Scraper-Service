# -*- coding: utf-8 -*-
"""
fl_verify_gaps.py - Close remaining verification gaps for fl.ru:

1. Python subcategory RSS ID scan (30-200) with proper UTF-8 output
2. Verify budget visibility via HTML parsing (CSS selectors)
3. Verify pagination (is there a page=2 link or not?)
4. Verify project card URL (ID + slug variant)
5. Check session/filter POST with category 31 returns JSON

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_verify_gaps.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx

# Fix Windows console encoding for Cyrillic
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def get_direct(url: str, headers: dict | None = None, timeout: float = 20.0) -> httpx.Response:
    h = {**BASE_HEADERS, **(headers or {})}
    with httpx.Client(timeout=timeout, headers=h, follow_redirects=True) as c:
        return c.get(url)


def parse_rss_channel_title(content: bytes) -> str:
    try:
        root = ET.fromstring(content)
        ch = root.find("channel")
        return ch.findtext("title", "") if ch else ""
    except Exception:
        return ""


def scan_python_subcategory(start=30, end=200):
    """Scan subcategory IDs for Python/AI/ML-related RSS feeds."""
    print(f"\n=== Scanning subcategory IDs {start}-{end} for Python/ML... ===")
    results = {}
    found_interesting = []

    for sub_id in range(start, end + 1):
        url = f"https://www.fl.ru/rss/all.xml?category=5&subcategory={sub_id}"
        try:
            resp = get_direct(url, headers={"Accept": "application/rss+xml, */*"}, timeout=15)
            if resp.status_code == 200 and (
                b"<?xml" in resp.content[:100] or b"<rss" in resp.content[:100]
            ):
                title = parse_rss_channel_title(resp.content)
                item_count = len(ET.fromstring(resp.content).findall(".//item"))
                result = {
                    "url": url,
                    "channel_title": title,
                    "item_count": item_count,
                }
                results[f"sub_{sub_id}"] = result

                # Check if it's interesting (has items or title contains Python/ML/AI)
                title_lower = title.lower()
                if item_count > 0 or any(
                    kw in title_lower
                    for kw in ["python", "ml", "ai", "machine", "data", "нейрон", "искусственный"]
                ):
                    found_interesting.append(result)
                    print(f"  sub={sub_id}: '{title}' ({item_count} items) *** INTERESTING ***")
                else:
                    if sub_id % 10 == 0:
                        print(f"  sub={sub_id}: '{title}' ({item_count} items)")
            else:
                results[f"sub_{sub_id}"] = {"status": resp.status_code}
        except Exception as e:
            results[f"sub_{sub_id}"] = {"error": str(e)[:80]}

    # Also scan category=31 (AI) subcategories
    print("\n--- Scanning category=31 (AI) subcategories 1-100 ---")
    for sub_id in range(1, 101):
        url = f"https://www.fl.ru/rss/all.xml?category=31&subcategory={sub_id}"
        try:
            resp = get_direct(url, headers={"Accept": "application/rss+xml, */*"}, timeout=15)
            if resp.status_code == 200 and b"<?xml" in resp.content[:100]:
                title = parse_rss_channel_title(resp.content)
                item_count = len(ET.fromstring(resp.content).findall(".//item"))
                if item_count > 0 or (title and "Фри-ланс)" not in title):
                    found_interesting.append({
                        "url": url, "channel_title": title, "item_count": item_count
                    })
                    print(f"  cat=31 sub={sub_id}: '{title}' ({item_count} items) *** INTERESTING ***")
        except Exception:
            pass

    return results, found_interesting


def check_budget_visibility():
    """Verify budget field is visible anonymously in HTML listing."""
    print("\n=== Budget visibility check ===")
    url = "https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/"
    resp = get_direct(url)
    html = resp.text
    print(f"  Status: {resp.status_code}, length: {len(html)}")

    # Find b-post__price blocks
    price_blocks = re.findall(
        r'<div[^>]*b-post__price[^>]*>.*?</div>',
        html,
        re.DOTALL
    )
    print(f"  Price blocks found: {len(price_blocks)}")
    for i, pb in enumerate(price_blocks[:5]):
        clean = re.sub(r'\s+', ' ', pb).strip()
        print(f"    [{i}] {clean[:200]}")

    # Also check span.text-4 inside price blocks
    amounts = re.findall(r'<span[^>]*text-4[^>]*>(.*?)</span>', html, re.DOTALL)
    amounts_clean = [re.sub(r'\s+', ' ', a).strip() for a in amounts if a.strip()]
    print(f"  Budget amount spans (text-4): {amounts_clean[:10]}")

    # Look for data-disposable-project-id
    ids_with_title = re.findall(
        r'data-disposable-project-id="(\d+)"[^>]*>(.*?)</a>',
        html,
        re.DOTALL
    )
    print(f"  Projects with data-disposable-project-id: {len(ids_with_title)}")
    for pid, title in ids_with_title[:3]:
        print(f"    ID={pid} title='{re.sub(chr(10), ' ', title).strip()[:80]}'")

    return {
        "status": resp.status_code,
        "price_blocks_count": len(price_blocks),
        "amount_samples": amounts_clean[:10],
        "project_id_count": len(ids_with_title),
    }


def check_pagination():
    """Verify pagination: is there a page=2 link, offset param, or cursor?"""
    print("\n=== Pagination check ===")
    url = "https://www.fl.ru/projects/category/programmirovanie/python/"
    resp = get_direct(url)
    html = resp.text

    # Check for pagination links
    page_links = re.findall(r'href="[^"]*(?:page|offset|cursor)[^"]*"', html)
    print(f"  Pagination links found: {page_links[:10]}")

    # Check for "next page" or arrow links
    next_links = re.findall(r'href="([^"]*)"[^>]*>[^<]*(?:Следующая|next|›|»)[^<]*<', html, re.IGNORECASE)
    print(f"  Next page links: {next_links[:5]}")

    # Look for pagination div
    pag_divs = re.findall(r'<div[^>]*pag[^>]*>.*?</div>', html, re.DOTALL | re.IGNORECASE)
    if pag_divs:
        print(f"  Pagination divs: {pag_divs[0][:300]}")

    # Count project IDs to see how many are on the page
    pids = re.findall(r'/projects/(\d{5,8})/', html)
    pids = list(dict.fromkeys(pids))
    print(f"  Unique project IDs on page: {len(pids)}")

    # Check if there's any "show more" / infinite scroll indicator
    show_more = re.findall(r'(?:load.more|show.more|Загрузить|Показать еще)', html, re.IGNORECASE)
    print(f"  Load more indicators: {show_more[:5]}")

    return {
        "page_links": page_links[:10],
        "next_links": next_links[:5],
        "project_count_on_page": len(pids),
        "show_more_found": bool(show_more),
    }


def check_project_card(project_id="5509193"):
    """Verify project card URL pattern and visible fields."""
    print(f"\n=== Project card check (ID={project_id}) ===")

    # Try both URL variants
    for url in [
        f"https://www.fl.ru/projects/{project_id}/",
        f"https://www.fl.ru/projects/{project_id}/kartochka.html",
    ]:
        resp = get_direct(url)
        html = resp.text
        final_url = str(resp.url)
        print(f"  URL: {url} -> {final_url} (status={resp.status_code})")

        if resp.status_code == 200:
            # Title
            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            title = re.sub(r'\s+', ' ', title_m.group(1)).strip()[:120] if title_m else ""
            print(f"    Title: {title}")

            # Budget
            budget_m = re.search(r'(?:бюджет|budget)[^>]*:.*?(\d[\d\s]+(?:руб|₽))', html[:5000], re.IGNORECASE)
            print(f"    Budget mention: {budget_m.group(0)[:80] if budget_m else 'not found'}")

            # Category
            cat_m = re.search(r'<div[^>]*b-post__category[^>]*>(.*?)</div>', html, re.DOTALL)
            cat = re.sub(r'\s+', ' ', cat_m.group(1)).strip()[:100] if cat_m else ""
            print(f"    Category block: {cat}")

            # anonymous UID
            uid_m = re.search(r'current-uid.*?content="(\d+)"', html)
            print(f"    current-uid: {uid_m.group(1) if uid_m else 'not found'}")

    return {"checked": True, "project_id": project_id}


def check_session_filter_post():
    """Test the session/filter POST endpoint with category filter."""
    print("\n=== session/filter POST test ===")
    # First get a CSRF token from the projects page
    resp = get_direct("https://www.fl.ru/projects/")
    html = resp.text
    csrf = re.search(r'meta[^>]+csrf-token[^>]+content="([^"]+)"', html)
    phpsessid = None
    for h, v in resp.headers.items():
        if h.lower() == "set-cookie" and "PHPSESSID" in v:
            m = re.search(r'PHPSESSID=([^;]+)', v)
            if m:
                phpsessid = m.group(1)

    csrf_token = csrf.group(1) if csrf else ""
    print(f"  CSRF token: {csrf_token[:20]}...")
    print(f"  PHPSESSID: {phpsessid}")

    if not csrf_token:
        print("  No CSRF token — cannot test POST")
        return {"error": "no_csrf"}

    # Build cookie string
    cookie_str = ""
    if phpsessid:
        cookie_str = f"PHPSESSID={phpsessid}"

    # POST to session/filter with category 31 (AI)
    headers = {
        **BASE_HEADERS,
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://www.fl.ru/projects/",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    post_data = {
        "active": True,
        "professions": [],
        "prof_groups": [31],  # AI category
        "cost_min": {"amount": 0, "currency": "RUB"},
        "cost_max": {"amount": 0, "currency": "RUB"},
        "without_cost": True,
        "keywords": [],
        "safe_deal": False,
        "pro": True,
        "verified": None,
        "urgent": False,
        "without_executor": False,
        "without_pro": False,
        "country_id": 0,
        "city_id": 0,
        "my_specs": False,
        "less_offers": False,
        "pro_only": True,
        "konkurs_end_days_from": None,
        "konkurs_end_days_to": None,
    }

    with httpx.Client(timeout=20, follow_redirects=True) as c:
        try:
            post_resp = c.post(
                "https://www.fl.ru/projects/session/filter/",
                json=post_data,
                headers=headers,
            )
            print(f"  POST status: {post_resp.status_code}")
            print(f"  POST response: {post_resp.text[:500]}")
            return {
                "post_status": post_resp.status_code,
                "post_response": post_resp.text[:500],
            }
        except Exception as e:
            print(f"  POST failed: {e}")
            return {"error": str(e)}


def main():
    print("=" * 60)
    print("FL.RU VERIFICATION — GAPS CLOSURE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    all_results = {}

    # 1. Python subcategory scan
    sub_results, interesting = scan_python_subcategory(start=30, end=200)
    all_results["subcategory_scan"] = {
        "interesting_found": interesting,
        "total_scanned": len(sub_results),
    }

    # 2. Budget visibility
    budget_info = check_budget_visibility()
    all_results["budget_visibility"] = budget_info

    # 3. Pagination
    pag_info = check_pagination()
    all_results["pagination"] = pag_info

    # 4. Project card
    card_info = check_project_card("5509193")
    all_results["project_card"] = card_info

    # 5. Session filter POST
    filter_info = check_session_filter_post()
    all_results["session_filter_post"] = filter_info

    # Save
    out_path = SAMPLES / "fl_gaps_verification.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\nResults saved: {out_path}")

    print("\n=== SUMMARY ===")
    print(f"  Python/ML subcategory IDs found: {len(interesting)}")
    for i in interesting:
        print(f"    {i['url']} -> '{i['channel_title']}' ({i['item_count']} items)")
    print(f"  Budget visible anonymously: {bool(budget_info.get('amount_samples'))}")
    print(f"  Budget amounts: {budget_info.get('amount_samples', [])[:5]}")
    print(f"  Projects per page (HTML): {pag_info.get('project_count_on_page')}")
    print(f"  Pagination links: {pag_info.get('page_links', [])[:3]}")
    print(f"  Session filter POST: {filter_info.get('post_status')}")


if __name__ == "__main__":
    main()
