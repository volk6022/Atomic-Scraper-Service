"""
avito_extract_mfe.py - extract listing items from the MFE state JSON blob.

The item list is in: <script type="mime/invalid" data-mfe-state="true">{...}</script>
Path: .state.catalog.items[] (or deeper via .state.<some-key>.catalog.items[])

Run from repo root:
  uv run python experiment-avito\\avito_extract_mfe.py
"""
import httpx, json, re, io, sys, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
SAMPLES = Path(__file__).parent / "samples"


def extract_mfe_items(html: str) -> tuple[list[dict], dict]:
    """
    Extract item list from <script type='mime/invalid' data-mfe-state='true'> block.

    Returns (items_list, meta_dict)
    """
    m = re.search(
        r'<script[^>]+type=["\']mime/invalid["\'][^>]+data-mfe-state=["\']true["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return [], {"error": "MFE state block not found"}

    content = m.group(1)
    try:
        data = json.loads(content)
    except Exception as e:
        return [], {"error": f"JSON parse failed: {e}"}

    # Navigate to catalog
    state = data.get("state", {})

    def find_catalog(obj, depth=0):
        if depth > 6:
            return None
        if isinstance(obj, dict):
            if "catalog" in obj and isinstance(obj["catalog"], dict):
                cat = obj["catalog"]
                if "items" in cat and isinstance(cat["items"], list):
                    return cat
            for v in obj.values():
                result = find_catalog(v, depth + 1)
                if result:
                    return result
        return None

    catalog = find_catalog(state)
    if not catalog:
        return [], {"error": "catalog not found in state", "state_keys": list(state.keys())[:20]}

    raw_items = catalog.get("items", [])
    total_count = None
    count_m = re.search(r'"count":(\d+),"totalCount"', content)
    if count_m:
        total_count = int(count_m.group(1))

    items = []
    for raw in raw_items:
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        price = raw.get("priceDetailed") or {}
        sort_ts = raw.get("sortTimeStamp")
        allow_ts = raw.get("allowTimeStamp")
        contacts = raw.get("contacts") or {}
        url_path = raw.get("urlPath", "")
        if "?" in url_path:
            url_path = url_path.split("?")[0]
        location = raw.get("location") or {}

        items.append({
            "id": str(raw["id"]),
            "title": raw.get("title", ""),
            "price_string": price.get("string", ""),
            "price_value": price.get("value"),
            "price_postfix": price.get("postfix", ""),
            "price_full_string": price.get("fullString", ""),
            "location": location.get("name", ""),
            "url": f"https://www.avito.ru{url_path}",
            "sort_timestamp_ms": sort_ts,
            "sort_datetime": str(datetime.datetime.fromtimestamp(sort_ts / 1000)) if sort_ts else None,
            "allow_timestamp_ms": allow_ts,
            "allow_datetime": str(datetime.datetime.fromtimestamp(allow_ts / 1000)) if allow_ts else None,
            "description_snippet": (raw.get("description") or "")[:200],
            "images_count": raw.get("imagesCount", 0),
            "phone_visible": contacts.get("phone", False),
            "message_enabled": contacts.get("message", False),
            "category": (raw.get("category") or {}).get("name", ""),
        })

    return items, {
        "total_count": total_count,
        "items_on_page": len(items),
        "sorts": catalog.get("sorts", []),
    }


def main():
    print("Fetching avito.ru/all/vakansii?s=104 ...")
    r = httpx.get("https://www.avito.ru/all/vakansii?s=104", headers=HEADERS, timeout=25, follow_redirects=True)
    html = r.text
    print(f"HTTP {r.status_code} | {len(html)} chars")

    items, meta = extract_mfe_items(html)
    print(f"\nExtracted: {len(items)} items | total={meta.get('total_count')}")

    if meta.get("error"):
        print(f"Error: {meta['error']}")
        return

    print("\nSample items (first 10):")
    for item in items[:10]:
        print(f"  [{item['id']}] {item['title'][:55]!r} | {item['price_full_string'][:30]} | {item['sort_datetime']}")

    # Test page 2
    print("\n\nFetching page 2 ...")
    r2 = httpx.get("https://www.avito.ru/all/vakansii?s=104&p=2", headers=HEADERS, timeout=25, follow_redirects=True)
    items2, meta2 = extract_mfe_items(r2.text)
    print(f"Page 2: {len(items2)} items")
    if items2:
        print(f"  First: [{items2[0]['id']}] {items2[0]['title'][:50]} | {items2[0]['sort_datetime']}")

    # Check ID overlap between pages
    ids1 = {i["id"] for i in items}
    ids2 = {i["id"] for i in items2}
    overlap = ids1 & ids2
    print(f"  ID overlap page1/page2: {len(overlap)}")

    # Save evidence
    evidence = {
        "url": "https://www.avito.ru/all/vakansii?s=104",
        "total_count": meta.get("total_count"),
        "items_count": len(items),
        "sample_items": items[:5],
        "page2_items_count": len(items2),
        "page12_id_overlap": len(overlap),
        "sorts": meta.get("sorts"),
        "data_source": "<script type='mime/invalid' data-mfe-state='true'>",
        "verified_2026_06_18": True,
    }
    ev_path = SAMPLES / "avito_mfe_evidence.json"
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidence saved: {ev_path}")


if __name__ == "__main__":
    main()
