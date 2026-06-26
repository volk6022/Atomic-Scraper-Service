# -*- coding: utf-8 -*-
"""
fl_rss_map_categories.py - Probe fl.ru RSS category/subcategory numeric IDs
by fetching each and reading the channel <title>.

We scan category=1..15 and subcategory=1..150 to build a mapping.
We stop when we find Programmirovanie (Programming), Python, and AI/ML.

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_rss_map_categories.py
"""
from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient  # noqa: E402

# Target keywords to find (lowercase match)
TARGETS = [
    "python",
    "программирование",
    "programmirovanie",
    "искусственный",
    "ai",
    "машинное",
    "machine",
]


def get_channel_title(content: bytes) -> str:
    """Extract RSS channel title from bytes."""
    try:
        root = ET.fromstring(content)
        ch = root.find("channel")
        if ch is not None:
            title_el = ch.find("title")
            if title_el is not None and title_el.text:
                return title_el.text.strip()
            # Handle CDATA
            return ""
        return ""
    except Exception:
        return ""


def get_item_count(content: bytes) -> int:
    try:
        root = ET.fromstring(content)
        ch = root.find("channel")
        if ch is not None:
            return len(ch.findall("item"))
        return 0
    except Exception:
        return 0


def probe_rss(client: ProxyRotatingClient, url: str) -> tuple[str, int]:
    """Returns (channel_title, item_count) or raises."""
    resp = client.get(url, headers={"Accept": "application/rss+xml, application/xml, */*"})
    if resp.status_code != 200:
        return f"HTTP_{resp.status_code}", 0
    ct = resp.headers.get("content-type", "")
    if "xml" not in ct and not resp.content.lstrip().startswith(b"<?xml"):
        return "NOT_RSS", 0
    title = get_channel_title(resp.content)
    count = get_item_count(resp.content)
    return title, count


def main():
    client = ProxyRotatingClient(max_retries=8, timeout=20.0)
    mapping = {}

    print("=== CATEGORY SCAN (category=1..20) ===")
    for cat_id in range(1, 21):
        url = f"https://www.fl.ru/rss/all.xml?category={cat_id}"
        try:
            title, count = probe_rss(client, url)
            mapping[f"category_{cat_id}"] = {"title": title, "items": count, "url": url}
            is_target = any(t in title.lower() for t in TARGETS)
            marker = " <-- TARGET!" if is_target else ""
            print(f"  category={cat_id:3d}: items={count:3d}  title={title[:60]}{marker}")
        except Exception as e:
            print(f"  category={cat_id:3d}: ERROR {e}")
            mapping[f"category_{cat_id}"] = {"error": str(e), "url": url}
        time.sleep(0.3)

    print()
    print("=== SUBCATEGORY SCAN (subcategory=1..200, step probe) ===")
    # First scan coarsely, then refine around hits
    found_programming = None
    found_ai = None

    # Coarse scan 1..200 step 1 (100 proxies available, each request is fast)
    for sub_id in range(1, 201):
        url = f"https://www.fl.ru/rss/all.xml?subcategory={sub_id}"
        try:
            title, count = probe_rss(client, url)
            mapping[f"subcategory_{sub_id}"] = {"title": title, "items": count, "url": url}
            is_target = any(t in title.lower() for t in TARGETS)
            if is_target or count > 0:
                marker = " <-- TARGET!" if is_target else ""
                print(f"  subcategory={sub_id:4d}: items={count:3d}  title={title[:70]}{marker}")
                if is_target and "python" in title.lower():
                    found_programming = sub_id
                if is_target and ("искусственный" in title.lower() or "ai" in title.lower() or "машинное" in title.lower()):
                    found_ai = sub_id
            else:
                # Print zero-result ones briefly
                if sub_id % 20 == 0:
                    print(f"  ... scanned up to subcategory={sub_id} ...")
        except Exception as e:
            print(f"  subcategory={sub_id:4d}: ERROR {e}")
            mapping[f"subcategory_{sub_id}"] = {"error": str(e), "url": url}
        time.sleep(0.2)

    # Save mapping
    out_path = SAMPLES / "fl_category_mapping.json"
    out_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nMapping saved: {out_path}")

    # Print found targets
    print("\n=== TARGET CATEGORIES FOUND ===")
    for key, val in mapping.items():
        title = val.get("title", "")
        if any(t in title.lower() for t in TARGETS):
            print(f"  {key}: {title} (items={val.get('items', 0)})")

    if found_programming:
        print(f"\nPython subcategory ID: {found_programming}")
    if found_ai:
        print(f"AI/ML subcategory ID: {found_ai}")


if __name__ == "__main__":
    main()
