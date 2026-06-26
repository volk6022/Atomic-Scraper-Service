"""
Card-parsing quality test for all 8 sites.
Samples up to 5 items per site from run_4 JSON, calls detail_<site>,
records per-field coverage, saves results to card_test/card_parse_results.json.

Run from repo root:
  uv run python experiment_monitoring\prototype\_card_parse_test.py
"""
from __future__ import annotations
import json
import sys
import time
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Site-specific target fields (what we want detail_* to return)
# ---------------------------------------------------------------------------
SITE_FIELDS = {
    "hh":       ["title", "amount", "description", "company", "date", "location", "skills", "url"],
    "avito":    ["title", "amount", "description", "company", "date", "location", "url"],
    "superjob": ["title", "amount", "description", "company", "date", "location", "url"],
    "habr":     ["title", "amount", "description", "company", "date", "skills", "url"],
    "zarplata": ["title", "amount", "description", "company", "url"],
    "fl":       ["title", "amount", "description", "url"],
    "kwork":    ["title", "amount", "description", "url"],
    "youdo":    ["title", "amount", "description", "date", "url"],
}

# Field aliases: map canonical name → possible keys in detail output
FIELD_ALIASES = {
    "description": ["description", "description_preview"],
    "company":     ["company", "employer"],
    "location":    ["location", "area", "town"],
    "skills":      ["skills", "key_skills"],
    "date":        ["date", "created", "publication_date", "published_at"],
    "amount":      ["amount", "salary"],
}


def get_field(card: dict, field: str):
    """Return the value for a canonical field, checking aliases."""
    keys = FIELD_ALIASES.get(field, [field])
    for k in keys:
        v = card.get(k)
        if v is not None:
            return v
    return None


def is_nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict)):
        return len(v) > 0
    if isinstance(v, (int, float)):
        return v != 0
    return bool(str(v).strip())


def load_run4_items() -> dict[str, list[dict]]:
    """Load items from run_4 JSON, return {site: [items]}."""
    results_dir = Path(__file__).parent / "results"
    run4_files = sorted(results_dir.glob("run_4_*.json"))
    if not run4_files:
        print("ERROR: No run_4_*.json found in results/", flush=True)
        sys.exit(1)
    run4_path = run4_files[-1]
    print(f"Loading items from: {run4_path.name}", flush=True)
    with open(run4_path, encoding="utf-8") as f:
        data = json.load(f)
    by_site: dict[str, list[dict]] = {}
    for site, sdata in data.get("sites", {}).items():
        by_site[site] = sdata.get("items", [])
    return by_site


def main():
    # Import detail functions from prototype
    proto_dir = Path(__file__).parent
    sys.path.insert(0, str(proto_dir))
    from monitor_proto import (
        detail_hh, detail_avito, detail_superjob, detail_habr,
        detail_zarplata, detail_fl, detail_kwork, detail_youdo,
        collect_fl,
    )

    DETAIL_FUNCS = {
        "hh":       detail_hh,
        "avito":    detail_avito,
        "superjob": detail_superjob,
        "habr":     detail_habr,
        "zarplata": detail_zarplata,
        "fl":       detail_fl,
        "kwork":    detail_kwork,
        "youdo":    detail_youdo,
    }

    items_by_site = load_run4_items()

    # For fl: also do a fresh small collect to get budget-bearing items
    # (run_4 fl items have amount=None from RSS — we want to include items
    # whose LD+JSON has a price so we can prove the fix)
    print("Supplementing fl items with fresh RSS collect (to find budget-bearing projects)...", flush=True)
    try:
        fresh_fl = collect_fl(limit=30)
        # Merge: add fresh items not already in run_4 list
        existing_ids = {x["id"] for x in items_by_site.get("fl", [])}
        for x in fresh_fl:
            if x["id"] not in existing_ids:
                items_by_site.setdefault("fl", []).append(x)
                existing_ids.add(x["id"])
        print(f"  fl pool now: {len(items_by_site.get('fl', []))} items", flush=True)
    except Exception as e:
        print(f"  fl fresh collect failed: {e}", flush=True)

    output: dict[str, dict] = {}
    card_dir = Path(__file__).parent / "card_test"
    card_dir.mkdir(parents=True, exist_ok=True)

    SAMPLE_N = 5

    for site in ["hh", "avito", "superjob", "habr", "zarplata", "fl", "kwork", "youdo"]:
        fields = SITE_FIELDS[site]
        detail_fn = DETAIL_FUNCS[site]
        all_items = items_by_site.get(site, [])

        print(f"\n{'='*56}", flush=True)
        print(f"  {site.upper()} — {len(all_items)} items in pool", flush=True)
        print(f"{'='*56}", flush=True)

        # Deduplicate by id, take first SAMPLE_N
        seen: set[str] = set()
        sample: list[dict] = []
        for it in all_items:
            iid = it.get("id", "")
            if iid and iid not in seen:
                seen.add(iid)
                sample.append(it)
            if len(sample) >= SAMPLE_N:
                break

        if not sample:
            print(f"  SKIP: no items", flush=True)
            output[site] = {"sampled": 0, "coverage": {}, "cards": [], "error": "no items"}
            continue

        cards: list[dict] = []
        for it in sample:
            t0 = time.time()
            try:
                card = detail_fn(it)
                elapsed = time.time() - t0
                # Annotate card with parse metadata
                card["_id"] = it["id"]
                card["_elapsed"] = round(elapsed, 2)
                card["_error"] = None
                cards.append(card)
                # Print per-field summary
                field_summary = " ".join(
                    f"{f}={'Y' if is_nonempty(get_field(card, f)) else 'N'}"
                    for f in fields
                )
                print(
                    f"  id={it['id']:12s}  {field_summary}  ({elapsed:.1f}s)",
                    flush=True
                )
            except Exception as exc:
                elapsed = time.time() - t0
                err_str = f"{type(exc).__name__}: {exc}"
                cards.append({"_id": it["id"], "_elapsed": round(elapsed, 2), "_error": err_str})
                print(f"  id={it['id']:12s}  ERROR: {err_str[:80]}  ({elapsed:.1f}s)", flush=True)

        # Compute coverage
        coverage: dict[str, str] = {}
        for f in fields:
            ok_count = sum(
                1 for c in cards
                if c.get("_error") is None and is_nonempty(get_field(c, f))
            )
            total_parsed = sum(1 for c in cards if c.get("_error") is None)
            coverage[f] = f"{ok_count}/{total_parsed}"

        output[site] = {
            "sampled": len(sample),
            "parsed_ok": sum(1 for c in cards if c.get("_error") is None),
            "coverage": coverage,
            "cards": cards,
        }

        print(f"\n  Coverage: {coverage}", flush=True)

    # Save results
    out_path = card_dir / "card_parse_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n\nSaved: {out_path}", flush=True)

    # Print final matrix
    print("\n" + "=" * 70, flush=True)
    print("CARD-PARSING COVERAGE MATRIX", flush=True)
    print("=" * 70, flush=True)

    # Collect all fields seen
    all_fields = ["title", "amount", "description", "company", "date", "location", "skills", "url"]
    header = f"{'site':12s}" + "".join(f"{f:14s}" for f in all_fields)
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for site in ["hh", "avito", "superjob", "habr", "zarplata", "fl", "kwork", "youdo"]:
        cov = output.get(site, {}).get("coverage", {})
        row = f"{site:12s}" + "".join(
            f"{cov.get(f, 'N/A'):14s}" for f in all_fields
        )
        print(row, flush=True)


if __name__ == "__main__":
    main()
