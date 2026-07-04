# -*- coding: utf-8 -*-
"""
fl_rss_category_probe.py - Probe RSS with correct category IDs from prof_groups API.

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_rss_category_probe.py
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient  # noqa: E402

# Category IDs from prof_groups API
CATEGORIES_TO_TEST = [
    # (label, category_id)
    ("ai_31", 31),           # AI — искусственный интеллект (id=31 from prof_groups)
    ("programming_5", 5),    # Программирование (id=5 from prof_groups) — confirmed category=5 in RSS
    ("mobile_36", 36),       # Mobile
    ("automation_41", 41),   # Автоматизация бизнеса
]

# Subcategory IDs to test — will be found by the full subcategory scan
# For now test: subcategory=1..20 we've seen so far
SUBCATEGORIES_TARGET = list(range(1, 30))  # probe first 30


def parse_rss_info(content: bytes) -> dict:
    """Parse RSS channel title and item count."""
    try:
        root = ET.fromstring(content)
        ch = root.find("channel")
        if not ch:
            return {"error": "no channel"}
        title_el = ch.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        items = ch.findall("item")
        first = {}
        if items:
            item = items[0]
            first_title_el = item.find("title")
            first = {
                "title": first_title_el.text if first_title_el is not None else "",
                "link": item.findtext("link", ""),
                "pubDate": item.findtext("pubDate", ""),
                "category": item.findtext("category", ""),
            }
        return {"channel_title": title, "item_count": len(items), "first_item": first}
    except Exception as e:
        return {"error": str(e)}


def main():
    client = ProxyRotatingClient(max_retries=8, timeout=20.0)
    results = {}

    print("=== Category ID probing for RSS ===")
    for label, cat_id in CATEGORIES_TO_TEST:
        url = f"https://www.fl.ru/rss/all.xml?category={cat_id}"
        try:
            resp = client.get(url)
            info = parse_rss_info(resp.content)
            (SAMPLES / f"fl_rss_cat{cat_id}.xml").write_bytes(resp.content)
            results[label] = {"category_id": cat_id, "url": url, **info}
            title = info.get("channel_title", "")
            count = info.get("item_count", 0)
            first_title = info.get("first_item", {}).get("title", "")[:60]
            print(f"  category={cat_id}: {title[:60]}  items={count}")
            if first_title:
                print(f"    First: {first_title}")
        except Exception as e:
            print(f"  category={cat_id}: ERROR {e}")
            results[label] = {"error": str(e)}

    print()
    print("=== Subcategory scan for Programming subcategories ===")
    for sub_id in SUBCATEGORIES_TARGET:
        # Test subcategory with category=5 (Programming)
        url = f"https://www.fl.ru/rss/all.xml?category=5&subcategory={sub_id}"
        try:
            resp = client.get(url)
            info = parse_rss_info(resp.content)
            title = info.get("channel_title", "")
            count = info.get("item_count", 0)
            key = f"cat5_sub{sub_id}"
            results[key] = {"url": url, **info}
            if count > 0 and title != "Заказы на FL.ru (Фри-ланс)":
                print(f"  cat5+subcategory={sub_id}: {title[:70]}  items={count}")
        except Exception as e:
            results[f"cat5_sub{sub_id}"] = {"error": str(e)}

    # Save
    out = SAMPLES / "fl_rss_category_probe.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out}")

    print("\n=== Relevant results ===")
    for key, r in results.items():
        title = r.get("channel_title", "")
        if any(t in title.lower() for t in ["python", "программирование", "ai", "искусственный", "ml"]):
            print(f"  {key}: {title}  (items={r.get('item_count',0)})")


if __name__ == "__main__":
    main()
