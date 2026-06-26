"""
avito_decode_item.py - decode staticRouterHydrationData for item card and list all fields.

Run from repo root:
  uv run python experiment-avito\\avito_decode_item.py
"""
import json, re, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES = Path(__file__).parent / "samples"
html = (SAMPLES / "avito_item_card_full.html").read_text(encoding="utf-8", errors="replace")
print(f"HTML length: {len(html)}")

# Flexible pattern: match until ); (with optional \r\n or \n)
m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);', html, re.DOTALL)
if not m:
    print("Pattern not found, trying alternative...")
    idx = html.find("__staticRouterHydrationData")
    if idx >= 0:
        print(f"  Found at {idx}: {repr(html[idx:idx+200])}")
    sys.exit(1)

raw = m.group(1)
print(f"Raw matched length: {len(raw)}")

# Decode: the raw content is a JSON-escaped string
try:
    # Method 1: json.loads with surrounding quotes
    decoded_str = json.loads('"' + raw + '"')
    data = json.loads(decoded_str)
    print("Method 1 (json.loads) success")
except Exception as e:
    print(f"Method 1 failed: {e}")
    # Method 2: manual unescape
    decoded_str = raw.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\r', '').replace('\\/', '/')
    try:
        data = json.loads(decoded_str)
        print("Method 2 (manual unescape) success")
    except Exception as e2:
        print(f"Method 2 failed: {e2}")
        sys.exit(1)

loader = data.get("loaderData", {})
item_loader = loader.get("catalog-or-main-or-item", {})
print(f"\nitem_loader top-level keys: {list(item_loader.keys())}")


def find_item_recursively(obj, depth=0, path=""):
    """Find the main item dict (has id, title, description)."""
    if depth > 10:
        return None
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if "id" in keys and "title" in keys and "description" in keys and "priceDetailed" in keys:
            return obj, path
        for k, v in obj.items():
            result = find_item_recursively(v, depth + 1, f"{path}.{k}")
            if result:
                return result
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:10]):
            result = find_item_recursively(item, depth + 1, f"{path}[{i}]")
            if result:
                return result
    return None


result = find_item_recursively(item_loader)
if result:
    item, path = result
    print(f"\n=== ITEM found at path: {path} ===")
    for k, v in item.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            print(f"  {k}: {{dict with {len(v)} keys: {list(v.keys())[:8]}}}")
        elif isinstance(v, list):
            print(f"  {k}: [list len={len(v)}]")

    # Specific deep dives
    print("\n=== SELLER ===")
    seller = item.get("seller", {})
    if isinstance(seller, dict):
        for k, v in seller.items():
            print(f"  {k}: {str(v)[:100]}")

    print("\n=== PRICE DETAILED ===")
    price = item.get("priceDetailed", {})
    if isinstance(price, dict):
        for k, v in price.items():
            print(f"  {k}: {v}")

    print("\n=== CONTACTS ===")
    contacts = item.get("contacts", {})
    if isinstance(contacts, dict):
        print(f"  phone: {contacts.get('phone', 'N/A')}")
        print(f"  message: {contacts.get('message', 'N/A')}")

    # Save item JSON
    out_path = SAMPLES / "avito_item_extracted.json"
    out_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nItem JSON saved: {out_path}")
else:
    print("\nItem not found with standard keys. Exploring item_loader...")
    for k, v in item_loader.items():
        print(f"  {k}: {type(v).__name__} = {str(v)[:150]}")
