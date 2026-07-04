"""Debug: find where catalog items actually live in the hydration data."""
import httpx, json, re, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

r = httpx.get("https://www.avito.ru/all/vakansii?s=104", headers=HEADERS, timeout=25, follow_redirects=True)
html = r.text
print(f"HTTP {r.status_code} | {len(html)} chars")

m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);', html, re.DOTALL)
if not m:
    print("No hydration data found")
    sys.exit(1)

raw = m.group(1)
decoded_str = json.loads('"' + raw + '"')
data = json.loads(decoded_str)

loader = data.get("loaderData", {})
item_loader = loader.get("catalog-or-main-or-item", {})
print(f"item_loader top keys: {list(item_loader.keys())[:20]}")

# Walk into catalog
for k in item_loader:
    v = item_loader[k]
    if isinstance(v, dict):
        print(f"  {k}: dict{list(v.keys())[:10]}")
        if "catalog" in v or "items" in v:
            print(f"    *** has catalog/items! ***")
            if "catalog" in v:
                cat = v["catalog"]
                print(f"    catalog keys: {list(cat.keys())[:10] if isinstance(cat, dict) else type(cat)}")
                if isinstance(cat, dict) and "items" in cat:
                    items = cat["items"]
                    print(f"    items count: {len(items) if isinstance(items, list) else 'not list'}")
                    if isinstance(items, list) and items:
                        first = items[0]
                        print(f"    first item keys: {list(first.keys())[:15] if isinstance(first, dict) else type(first)}")
    elif isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")

# Save the item_loader as JSON for inspection
SAMPLES = Path(__file__).parent / "samples"
(SAMPLES / "avito_item_loader_listing.json").write_text(
    json.dumps(item_loader, ensure_ascii=False, indent=2)[:500000], encoding="utf-8"
)
print(f"\nSaved item_loader to samples/avito_item_loader_listing.json")
