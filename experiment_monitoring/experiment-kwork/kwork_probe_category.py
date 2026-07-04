"""
kwork_probe_category.py — Verify category filtering on POST /projects.

Key finding from base_response.json:
  - data.pagination.data = list of 12 project objects (the actual list!)
  - data.wants = same list
  - data.wants_20891_data = empty (matched-profile list, requires login state)
  - pagination.total = 494, last_page = 42, per_page = 12

This script:
  1. Confirms c=79 filters to ML/AI category
  2. Confirms c=11 for Python
  3. Tests page parameter on pagination
  4. Maps category IDs from the HTML category tree
  5. Tests query text search
  6. Saves sample ML/Python projects

Run from repo root:
  uv run python experiment-kwork/kwork_probe_category.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES_DIR = Path(__file__).parent / "samples" / "xhr"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

XHR_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://kwork.ru/projects",
    "Origin": "https://kwork.ru",
}


def post_projects(params: dict) -> dict:
    with httpx.Client(headers=XHR_HEADERS, follow_redirects=True, timeout=20.0) as c:
        r = c.post("https://kwork.ru/projects", data=params)
    r.raise_for_status()
    return r.json()


def get_projects_list(data: dict) -> list[dict]:
    """Extract the actual project list from response data."""
    # Main list is in data.pagination.data or data.wants
    d = data.get("data", {})
    if "pagination" in d and "data" in d["pagination"]:
        return d["pagination"]["data"]
    if "wants" in d and d["wants"]:
        return d["wants"]
    return []


def probe(params: dict, label: str, save_as: str | None = None) -> list[dict]:
    print(f"\n[POST /projects] {label}")
    print(f"  params={params}")
    try:
        data = post_projects(params)
        projects = get_projects_list(data)
        pagination = data.get("data", {}).get("pagination", {})
        total = pagination.get("total", "?")
        last_page = pagination.get("last_page", "?")
        current = pagination.get("current_page", "?")
        per_page = pagination.get("per_page", "?")
        print(f"  total={total}  pages={last_page}  per_page={per_page}  current={current}")
        print(f"  projects_on_page={len(projects)}")
        for p in projects[:5]:
            cat = p.get("category_id", "?")
            pid = p.get("id", "?")
            name = p.get("name", "")
            price = p.get("priceLimit", "?")
            desc_preview = p.get("description", "")[:80]
            print(f"    [{cat}] id={pid} price={price} name={name[:50]!r}")
            print(f"           desc={desc_preview!r}")
        if save_as:
            # Save the cleaned-up evidence
            evidence = {
                "params": params,
                "total": total,
                "last_page": last_page,
                "per_page": per_page,
                "current_page": current,
                "projects_count": len(projects),
                "projects": projects[:20],
            }
            path = SAMPLES_DIR / save_as
            with open(path, "w", encoding="utf-8") as f:
                json.dump(evidence, f, ensure_ascii=False, indent=2)
            print(f"  Saved: {path}")
        return projects
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return []


if __name__ == "__main__":
    # 1. Baseline — all categories
    p_all = probe({}, "all categories baseline", "evidence_all.json")

    # 2. Category 79 — ML/AI
    p_79 = probe({"c": "79"}, "c=79 ML/AI", "evidence_cat79.json")
    # Check if actually filtered
    if p_79:
        cat_ids = set(p["category_id"] for p in p_79)
        print(f"  category_ids in result: {cat_ids}")

    # 3. Category 11 — Python dev
    p_11 = probe({"c": "11"}, "c=11 Python", "evidence_cat11.json")
    if p_11:
        cat_ids = set(p["category_id"] for p in p_11)
        print(f"  category_ids in result: {cat_ids}")

    # 4. Page 2 of all
    p_p2 = probe({"page": "2"}, "page=2 all categories")
    if p_all and p_p2:
        ids_p1 = {p["id"] for p in p_all}
        ids_p2 = {p["id"] for p in p_p2}
        print(f"  page1 ids: {sorted(ids_p1)[:5]}")
        print(f"  page2 ids: {sorted(ids_p2)[:5]}")
        print(f"  overlap: {ids_p1 & ids_p2}")
        print(f"  different_pages: {bool(ids_p2 - ids_p1)}")

    # 5. Page 2 of ML/AI
    p_79_p2 = probe({"c": "79", "page": "2"}, "c=79 page=2")

    # 6. Test query search
    probe({"q": "Python"}, "query=Python")
    probe({"query": "Python"}, "query field: query=Python")
    probe({"search": "Python"}, "search=Python")

    # 7. Category list from HTML — let's find the category tree
    print("\n--- Fetching category list from HTML ---")
    with httpx.Client(
        headers={
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        follow_redirects=True,
        timeout=20.0,
    ) as c:
        r = c.get("https://kwork.ru/projects")
    html = r.text

    # Extract category data from window.config or similar
    # Look for category tree in JS variables
    cat_json_m = re.search(r'"categories"\s*:\s*(\[[^\]]{100,}?\])', html, re.DOTALL)
    if cat_json_m:
        print(f"  Found categories array in HTML")
        try:
            cats = json.loads(cat_json_m.group(1))
            print(f"  {len(cats)} categories:")
            for cat in cats[:20]:
                print(f"    id={cat.get('id',cat.get('ID','?'))} name={cat.get('name',cat.get('title','?'))!r}")
            with open(SAMPLES_DIR / "categories_from_html.json", "w", encoding="utf-8") as f:
                json.dump(cats, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"  Parse error: {exc}")
    else:
        # Try to find individual category entries
        # Pattern: {"id":N,"name":"CategoryName"} or catId:N catName:'...'
        # Also look at the category filter section
        cat_names_with_ids = re.findall(
            r'"(?:id|ID)"\s*:\s*(\d+)[^}]{0,200}"(?:name|title|TITLE|seoH1|NAME)"\s*:\s*"([^"]{3,60})"',
            html,
        )
        print(f"  Found {len(cat_names_with_ids)} id+name pairs in HTML:")
        for cid, cname in cat_names_with_ids[:30]:
            print(f"    {cid}: {cname!r}")
        if cat_names_with_ids:
            with open(SAMPLES_DIR / "category_ids_from_html.json", "w", encoding="utf-8") as f:
                json.dump([{"id": k, "name": v} for k, v in cat_names_with_ids], f, ensure_ascii=False, indent=2)

    # 8. Identify category IDs from actual project data
    print("\n--- Category IDs seen in live responses ---")
    all_seen: dict[str, list[str]] = {}
    for project in (p_all + p_79 + p_11):
        cat_id = str(project.get("category_id", ""))
        name = project.get("name", "")
        if cat_id:
            all_seen.setdefault(cat_id, []).append(name[:40])
    for cat_id, names in sorted(all_seen.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        print(f"  cat={cat_id}: {names[0]!r}")

    # 9. Check if category 79 really filters
    print(f"\n--- Category 79 filter check ---")
    if p_79:
        cat_ids_79 = [p.get("category_id") for p in p_79]
        unique = set(cat_ids_79)
        print(f"  c=79 returns categories: {unique}")
        is_filtered = unique == {"79"} or (len(unique) == 1)
        print(f"  Actually filtered to 79 only: {is_filtered}")
    else:
        print("  No results for c=79")

    print("\nDone.")
