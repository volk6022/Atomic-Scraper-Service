"""
avito_parse_item_json.py - properly decode and parse the item card JSON.

Run from repo root:
  uv run python experiment-avito\\avito_parse_item_json.py
"""
from __future__ import annotations
import json, re, io, sys, urllib.parse
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES = Path(__file__).parent / "samples"


def deep_search(obj, target_keys: list, path: str = "", depth: int = 0, results: list | None = None) -> list:
    """Recursively find keys in nested JSON."""
    if results is None:
        results = []
    if depth > 12:
        return results
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_path = f"{path}.{k}" if path else k
            if any(tk.lower() in k.lower() for tk in target_keys):
                val_str = json.dumps(v, ensure_ascii=False)[:200] if not isinstance(v, str) else v[:200]
                results.append((full_path, val_str))
            deep_search(v, target_keys, full_path, depth + 1, results)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:20]):
            deep_search(item, target_keys, f"{path}[{i}]", depth + 1, results)
    return results


def main():
    html_path = SAMPLES / "avito_item_card.html"
    if not html_path.exists():
        print("avito_item_card.html not found, run avito_item_card_probe.py first")
        return

    html = html_path.read_text(encoding="utf-8", errors="replace")

    # Decode __staticRouterHydrationData properly using json.loads on the JS string
    m = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);\s*\n', html, re.DOTALL)
    if not m:
        print("staticRouterHydrationData not found")
        return

    raw_escaped = m.group(1)
    # json.loads handles the JS-style escape sequences properly
    try:
        decoded_str = json.loads(f'"{raw_escaped}"')
        data = json.loads(decoded_str)
        print("staticRouterHydrationData decoded successfully")
        print(f"Top-level keys: {list(data.keys())}")
    except Exception as e:
        print(f"Decode error: {e}")
        # Fallback: urllib.parse.unquote
        try:
            decoded_str = urllib.parse.unquote(raw_escaped)
            data = json.loads(decoded_str)
            print("Decoded via urllib.parse.unquote")
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            return

    # Navigate to item data
    loader = data.get("loaderData", {})
    item_loader = loader.get("catalog-or-main-or-item", {})
    print(f"\nitem_loader keys: {list(item_loader.keys())[:30]}")

    # Save full JSON
    out_path = SAMPLES / "avito_item_card_decoded.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2)[:500000], encoding="utf-8")
    print(f"Saved full decoded JSON: {out_path}")

    # Deep search for important fields
    search_keys = ["title", "price", "salary", "description", "seller", "company",
                   "employer", "location", "address", "phone", "contact",
                   "date", "time", "stamp", "category", "experience", "schedule",
                   "userId", "userName", "shopId", "profile", "rating", "status"]

    print("\n=== Deep field search ===")
    results = deep_search(data, search_keys)
    seen_keys = set()
    for path, val in results:
        short_key = path.split(".")[-1]
        if short_key not in seen_keys and len(results) < 200:
            seen_keys.add(short_key)
            print(f"  {path} = {val[:120]}")

    # Specifically dump the item_loader as flat JSON for inspection
    if item_loader:
        print(f"\n=== item_loader structure (first 3000 chars) ===")
        il_json = json.dumps(item_loader, ensure_ascii=False, indent=2)
        print(il_json[:3000])


if __name__ == "__main__":
    main()
