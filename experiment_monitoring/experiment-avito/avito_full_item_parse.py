"""
avito_full_item_parse.py - fetch item card with FULL content and extract all fields.

Run from repo root:
  uv run python experiment-avito\\avito_full_item_parse.py
"""
from __future__ import annotations
import httpx, json, re, io, sys, urllib.parse, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS_LIST = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Cache-Control": "no-cache",
}

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(parents=True, exist_ok=True)


def get_first_item_from_listing() -> tuple[str, str, str]:
    """Get first item's id, urlPath, title from the listing."""
    r = httpx.get("https://www.avito.ru/all/vakansii?s=104", headers=HEADERS_LIST, timeout=25, follow_redirects=True)
    html = r.text
    m = re.search(
        r'"id":(\d{10,12}),"categoryId":\d+,"microCategoryId":\d+,"locationId":\d+.*?"urlPath":"((?:/[^"?]+){2,})',
        html, re.DOTALL
    )
    if m:
        item_id = m.group(1)
        url_path = m.group(2).split("?")[0]
        title_m = re.search(r'"title":"((?:[^"\\]|\\.){3,80})"', html)
        title = title_m.group(1) if title_m else "unknown"
        return item_id, f"https://www.avito.ru{url_path}", title
    return "8171068536", "https://www.avito.ru/moskva/vakansii/sborschik_zakazov_gipermakret_na_leto_8171068536", "unknown"


def main():
    print("Step 1: Get item URL from listing...")
    item_id, item_url, title = get_first_item_from_listing()
    print(f"  id={item_id} title={title}")
    print(f"  url={item_url}")

    print(f"\nStep 2: Fetch full item card...")
    r = httpx.get(
        item_url,
        headers={**HEADERS_LIST, "Referer": "https://www.avito.ru/all/vakansii?s=104"},
        timeout=30, follow_redirects=True
    )
    html = r.text
    print(f"  HTTP {r.status_code} | {len(html)} chars")

    # Save full HTML
    (SAMPLES / "avito_item_card_full.html").write_text(html, encoding="utf-8", errors="replace")
    print(f"  Saved full HTML: {len(html)} chars")

    # Decode staticRouterHydrationData
    m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);\n', html, re.DOTALL)
    if m:
        raw = m.group(1)
        try:
            decoded_str = json.loads(f'"{raw}"')
            data = json.loads(decoded_str)
            print(f"\nDecoded staticRouterHydrationData: {len(decoded_str)} chars")
        except Exception as e:
            print(f"  Decode error: {e}")
            # Try simple unescaping
            decoded_str = raw.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\r', '')
            try:
                data = json.loads(decoded_str)
            except Exception as e2:
                print(f"  Fallback error: {e2}")
                data = {}
    else:
        print("staticRouterHydrationData not found (checking pattern...)")
        m2 = re.search(r'__staticRouterHydrationData', html)
        if m2:
            print(f"  Variable found at index {m2.start()}")
            ctx = html[m2.start():m2.start()+200]
            print(f"  Context: {ctx}")
        data = {}

    if data:
        loader = data.get("loaderData", {})
        item_loader = loader.get("catalog-or-main-or-item", {})

        # Save as formatted JSON
        out_path = SAMPLES / "avito_item_loader.json"
        out_path.write_text(json.dumps(item_loader, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved item_loader.json: {len(json.dumps(item_loader))} chars")

        # Extract key fields directly from decoded JSON
        print("\n=== ITEM CARD FIELDS ===")

        def jget(d, *keys, default="NOT_FOUND"):
            for k in keys:
                if isinstance(d, dict) and k in d:
                    d = d[k]
                else:
                    return default
            return d

        # Navigate into item_loader to find the actual item data
        item_data = jget(item_loader, "initialData", "data", "item")
        if item_data == "NOT_FOUND":
            item_data = jget(item_loader, "data", "item")
        if item_data == "NOT_FOUND":
            # Search through all keys
            print("Searching for item data...")
            print(f"item_loader keys: {list(item_loader.keys())[:20]}")
            for k, v in item_loader.items():
                if isinstance(v, dict):
                    print(f"  {k}: {list(v.keys())[:15]}")
        else:
            print(f"  id: {jget(item_data, 'id')}")
            print(f"  title: {jget(item_data, 'title')}")
            print(f"  description: {str(jget(item_data, 'description'))[:200]}")
            print(f"  price: {jget(item_data, 'priceDetailed', 'string')}")
            print(f"  location: {jget(item_data, 'location', 'name')}")
            print(f"  timestamp: {jget(item_data, 'time', 'date')}")
            print(f"  categoryName: {jget(item_data, 'category', 'name')}")
            print(f"  seller.id: {jget(item_data, 'seller', 'sellerId')}")
            print(f"  seller.name: {jget(item_data, 'seller', 'name')}")
            print(f"  contacts: {jget(item_data, 'contacts', 'list')}")

    # Also extract items from listing for verification summary
    print("\n=== Extracting items from listing page for summary ===")
    listing_r = httpx.get("https://www.avito.ru/all/vakansii?s=104", headers=HEADERS_LIST, timeout=25, follow_redirects=True)
    listing_html = listing_r.text
    item_matches = re.findall(
        r'"id":(\d{10,12}),"categoryId":\d+,"microCategoryId":\d+,"locationId":(\d+).*?'
        r'"title":"((?:[^"\\]|\\.){3,80})".*?"priceDetailed":\{"enabled":(true|false).*?"string":"([^"]*)".*?"sortTimeStamp":(\d{13})',
        listing_html[:2000000], re.DOTALL
    )

    print(f"  Items matched: {len(item_matches)}")
    print("  Sample items:")
    for iid, loc_id, title, price_enabled, price_str, ts in item_matches[:5]:
        ts_dt = datetime.datetime.fromtimestamp(int(ts) / 1000)
        title_clean = title.replace("\\n", " ").replace("\\u0026", "&")[:60]
        print(f"    [{iid}] {title_clean} | {price_str} | {ts_dt}")


if __name__ == "__main__":
    main()
