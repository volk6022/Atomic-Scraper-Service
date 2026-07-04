"""
avito_item_card_probe.py - fetch a real vacancy item card and extract fields.

Run from repo root:
  uv run python experiment-avito\\avito_item_card_probe.py
"""
from __future__ import annotations
import httpx, json, re, io, sys, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Referer": "https://www.avito.ru/all/vakansii?s=104",
}

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(parents=True, exist_ok=True)


def get_first_item_url_from_listing() -> tuple[str, str]:
    """Get first item's urlPath from the listing page."""
    r = httpx.get(
        "https://www.avito.ru/all/vakansii?s=104",
        headers={k: v for k, v in HEADERS.items() if k != "Referer"},
        timeout=25, follow_redirects=True
    )
    html = r.text
    # Find first urlPath
    m = re.search(r'"urlPath":"((?:/[a-z0-9_\-]+){2,}/[a-z0-9_\-]+_\d{5,12}(?:\?[^"]*)?)"', html)
    if m:
        item_id_m = re.search(r'"id":(\d{10,12}),"categoryId"', html)
        item_id = item_id_m.group(1) if item_id_m else "unknown"
        url_path = m.group(1).split("?")[0]  # strip context query
        return item_id, f"https://www.avito.ru{url_path}"
    return "unknown", "https://www.avito.ru/moskva/vakansii/sborschik_zakazov_gipermakret_na_leto_8171068536"


def extract_item_card_fields(html: str) -> dict:
    """Extract all observable fields from an item card page."""
    fields = {}

    # Title
    m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.){3,150})"', html)
    if m:
        fields["title"] = m.group(1)

    # Description (try __preloadedState__ decoded)
    m = re.search(r'window\.__preloadedState__\s*=\s*"(.+?)";', html, re.DOTALL)
    if m:
        try:
            import urllib.parse
            decoded = urllib.parse.unquote(m.group(1))
            fields["preloadedState_len"] = len(decoded)
            # Try to find description in it
            dm = re.search(r'"description":"((?:[^"\\]|\\.){20,500})"', decoded)
            if dm:
                fields["description_snippet"] = dm.group(1)[:200]
            # Seller name
            sm = re.search(r'"sellerName":"([^"]+)"', decoded)
            if sm:
                fields["seller_name"] = sm.group(1)
            # Seller ID
            sm2 = re.search(r'"sellerId":(\d+)', decoded)
            if sm2:
                fields["seller_id"] = sm2.group(1)
            # User type
            um = re.search(r'"userType":"([^"]+)"', decoded)
            if um:
                fields["user_type"] = um.group(1)
        except Exception as e:
            fields["preloadedState_err"] = str(e)

    # Price/salary
    m = re.search(r'"priceDetailed":\{"enabled":true,"fullString":"([^"]+)"', html)
    if m:
        fields["price_full_string"] = m.group(1)

    # Item ID
    m = re.search(r'"id":(\d{10,12}),"categoryId"', html)
    if m:
        fields["item_id"] = m.group(1)

    # sortTimeStamp
    m = re.search(r'"sortTimeStamp":(\d{13})', html)
    if m:
        ts = int(m.group(1)) / 1000
        fields["sort_timestamp"] = m.group(1)
        fields["sort_datetime"] = str(datetime.datetime.fromtimestamp(ts))

    # allowTimeStamp (publish date)
    m = re.search(r'"allowTimeStamp":(\d{13})', html)
    if m:
        ts = int(m.group(1)) / 1000
        fields["allow_timestamp"] = m.group(1)
        fields["allow_datetime"] = str(datetime.datetime.fromtimestamp(ts))

    # Location
    m = re.search(r'"location":\{"id":\d+,"name":"([^"]+)"', html)
    if m:
        fields["location"] = m.group(1)

    # Phone available?
    m = re.search(r'"phone":(true|false)', html)
    if m:
        fields["phone_visible"] = m.group(1)

    # Category name
    m = re.search(r'"category":\{"id":\d+,"name":"([^"]+)"', html)
    if m:
        fields["category"] = m.group(1)

    # Look in HTML for data-qa attributes
    dqa = re.findall(r'data-qa="([^"]{3,50})"', html)
    fields["data_qa_attrs"] = list(set(dqa))[:30]

    # employer/company name
    m = re.search(r'"companyName":"([^"]+)"', html)
    if m:
        fields["company_name"] = m.group(1)

    # Look for contacts section
    m = re.search(r'"contacts":\{[^}]{20,400}\}', html)
    if m:
        fields["contacts_raw"] = m.group(0)[:300]

    return fields


def main():
    print("Step 1: Getting first item URL from listing...")
    item_id, item_url = get_first_item_url_from_listing()
    print(f"  item_id={item_id}")
    print(f"  item_url={item_url}")

    print(f"\nStep 2: Fetching item card: {item_url}")
    r = httpx.get(item_url, headers=HEADERS, timeout=25, follow_redirects=True)
    html = r.text
    print(f"  HTTP {r.status_code} | {len(html)} chars")

    # Save HTML
    (SAMPLES / "avito_item_card.html").write_bytes(html.encode("utf-8", errors="replace"))
    print(f"  Saved: {SAMPLES / 'avito_item_card.html'}")

    print("\nStep 3: Extracting fields...")
    fields = extract_item_card_fields(html)

    print("\n=== Extracted item card fields ===")
    for k, v in fields.items():
        if k == "data_qa_attrs":
            print(f"  {k}: {v[:10]}")
        else:
            val_str = str(v)
            print(f"  {k}: {val_str[:120]}")

    # Save evidence
    evidence = {
        "item_id": item_id,
        "item_url": item_url,
        "status": r.status_code,
        "html_len": len(html),
        "extracted_fields": {k: str(v)[:200] for k, v in fields.items()},
    }
    ev_path = SAMPLES / "avito_item_card_evidence.json"
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidence saved: {ev_path}")


if __name__ == "__main__":
    main()
