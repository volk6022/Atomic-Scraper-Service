"""
avito_buyeritem_extract.py - extract item card data from buyerItem key.

Run from repo root:
  uv run python experiment-avito\\avito_buyeritem_extract.py
"""
import json, re, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES = Path(__file__).parent / "samples"
html = (SAMPLES / "avito_item_card_full.html").read_text(encoding="utf-8", errors="replace")

m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);', html, re.DOTALL)
raw = m.group(1)
decoded_str = json.loads('"' + raw + '"')
data = json.loads(decoded_str)

item_loader = data["loaderData"]["catalog-or-main-or-item"]
buyer_item = item_loader.get("buyerItem", {})

print(f"buyerItem top-level keys: {list(buyer_item.keys())[:30]}")
print()

# Drill into item
item = buyer_item.get("item", {})
if item:
    print(f"=== item keys: {list(item.keys())[:40]} ===")
    for k, v in item.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            print(f"  {k}: {{dict {len(v)} keys: {list(v.keys())[:8]}}}")
        elif isinstance(v, list):
            print(f"  {k}: [list len={len(v)}]")

    # Deep dives
    print("\n=== SELLER (item.seller) ===")
    seller = item.get("seller", {})
    if seller:
        for k, v in seller.items():
            print(f"  {k}: {str(v)[:120]}")

    print("\n=== PRICE (item.priceDetailed) ===")
    price = item.get("priceDetailed", {})
    if price:
        for k, v in price.items():
            print(f"  {k}: {v}")

    print("\n=== CONTACTS ===")
    contacts = item.get("contacts", {})
    if contacts:
        for k, v in contacts.items():
            print(f"  {k}: {str(v)[:200]}")

    print("\n=== PARAMS/ATTRIBUTES ===")
    params = item.get("params", [])
    if params:
        for p in params[:10]:
            print(f"  {p}")

    # Save
    out_path = SAMPLES / "avito_item_extracted.json"
    out_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nItem JSON saved: {out_path}")
    print(f"Item JSON size: {len(json.dumps(item))} chars")
else:
    print("item not in buyerItem, checking sub-keys...")
    for k, v in buyer_item.items():
        print(f"  {k}: {type(v).__name__} = {str(v)[:150]}")
