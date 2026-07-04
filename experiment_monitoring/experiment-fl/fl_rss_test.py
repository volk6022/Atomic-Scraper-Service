# -*- coding: utf-8 -*-
"""
fl_rss_test.py - Verify fl.ru RSS feeds through rotating RU proxy.

Tests:
  1. Base feed: https://www.fl.ru/rss/all.xml
  2. Category variants with subcategory= and category= params
  3. Tries to discover category IDs for Python, ML/AI

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_rss_test.py
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient  # noqa: E402

# ---------------------------------------------------------------------------
# RSS URLs to probe
# ---------------------------------------------------------------------------

RSS_URLS = [
    # Base feed (no category filter)
    ("base", "https://www.fl.ru/rss/all.xml"),
    # Category-only variants (guessed IDs from community sources)
    ("category_3", "https://www.fl.ru/rss/all.xml?category=3"),
    ("category_1", "https://www.fl.ru/rss/all.xml?category=1"),
    # Subcategory variants (guessed IDs)
    ("subcat_python_guess", "https://www.fl.ru/rss/all.xml?subcategory=49"),
    ("subcat_ai_guess", "https://www.fl.ru/rss/all.xml?subcategory=51"),
    ("subcat_dev_guess", "https://www.fl.ru/rss/all.xml?subcategory=1"),
    # Combined
    ("cat3_sub49", "https://www.fl.ru/rss/all.xml?category=3&subcategory=49"),
    ("cat3_sub51", "https://www.fl.ru/rss/all.xml?category=3&subcategory=51"),
]

# Also try fetching the robots.txt and the raw category page to cross-reference
EXTRA_URLS = [
    ("robots_txt", "https://www.fl.ru/robots.txt"),
]


def parse_rss(content: bytes) -> dict:
    """Parse RSS XML and return summary dict."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}", "raw_preview": content[:500].decode(errors="replace")}

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    channel = root.find("channel")
    if channel is None:
        return {"error": "No <channel> element found", "raw_preview": content[:500].decode(errors="replace")}

    title = channel.findtext("title", "")
    items = channel.findall("item")

    parsed_items = []
    for item in items[:5]:  # First 5 items
        parsed_items.append({
            "title": item.findtext("title", ""),
            "link": item.findtext("link", ""),
            "guid": item.findtext("guid", ""),
            "pubDate": item.findtext("pubDate", ""),
            "description_snippet": (item.findtext("description", "") or "")[:200],
            # Budget field if exists
            "budget": item.findtext("budget", item.findtext("{*}budget", "")),
        })

    return {
        "channel_title": title,
        "item_count": len(items),
        "first_5_items": parsed_items,
    }


def main():
    client = ProxyRotatingClient(max_retries=15, timeout=30.0)
    results = {}

    print("=" * 60)
    print("FL.RU RSS VERIFICATION")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Test extra URLs first (robots.txt)
    for name, url in EXTRA_URLS:
        print(f"\n[{name}] GET {url}")
        try:
            resp = client.get(url)
            print(f"  Status: {resp.status_code}")
            print(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
            print(f"  Body snippet: {resp.text[:300]}")
            (SAMPLES / f"fl_{name}.txt").write_bytes(resp.content)
            results[name] = {
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "snippet": resp.text[:500],
                "headers": dict(resp.headers),
            }
        except Exception as e:
            print(f"  FAILED: {e}")
            results[name] = {"error": str(e)}

    # Test RSS URLs
    for name, url in RSS_URLS:
        print(f"\n[{name}] GET {url}")
        try:
            resp = client.get(url, headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"})
            print(f"  Status: {resp.status_code}")
            ct = resp.headers.get("content-type", "N/A")
            print(f"  Content-Type: {ct}")

            server = resp.headers.get("server", "N/A")
            print(f"  Server: {server}")

            # Check anti-bot headers
            for hdr in ["cf-ray", "x-ddos-guard", "x-ddos-protection", "__ddg1_", "__ddg2_",
                        "x-ddos-guard-id", "x-request-id"]:
                if hdr in resp.headers:
                    print(f"  Anti-bot header [{hdr}]: {resp.headers[hdr]}")

            (SAMPLES / f"fl_rss_{name}.xml").write_bytes(resp.content)

            if resp.status_code == 200 and (
                "xml" in ct.lower() or resp.content.lstrip().startswith(b"<?xml") or
                resp.content.lstrip().startswith(b"<rss")
            ):
                parsed = parse_rss(resp.content)
                print(f"  Items: {parsed.get('item_count', 0)}")
                if parsed.get("first_5_items"):
                    first = parsed["first_5_items"][0]
                    print(f"  First item title: {first['title'][:80]}")
                    print(f"  First item link: {first['link']}")
                    print(f"  First item pubDate: {first['pubDate']}")
                    if first.get("budget"):
                        print(f"  First item budget: {first['budget']}")
                results[name] = {
                    "status": resp.status_code,
                    "content_type": ct,
                    "server": server,
                    "rss_parsed": parsed,
                    "anti_bot_headers": {h: resp.headers[h] for h in ["cf-ray", "x-ddos-guard", "server"]
                                        if h in resp.headers},
                }
            else:
                snippet = resp.text[:600]
                print(f"  Not RSS XML — snippet: {snippet[:200]}")
                results[name] = {
                    "status": resp.status_code,
                    "content_type": ct,
                    "server": server,
                    "not_rss": True,
                    "snippet": snippet,
                }
        except Exception as e:
            print(f"  FAILED: {e}")
            results[name] = {"error": str(e)}

    # Save summary
    summary_path = SAMPLES / "fl_rss_results.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\nResults saved to: {summary_path}")
    print("\n=== SUMMARY ===")
    for name, r in results.items():
        if "error" in r:
            print(f"  {name}: ERROR — {r['error']}")
        elif r.get("not_rss"):
            print(f"  {name}: HTTP {r.get('status')} — NOT RSS (challenge/block?)")
        elif "rss_parsed" in r:
            cnt = r["rss_parsed"].get("item_count", 0)
            print(f"  {name}: HTTP {r.get('status')} — RSS OK, {cnt} items")
        else:
            print(f"  {name}: HTTP {r.get('status')}")


if __name__ == "__main__":
    main()
