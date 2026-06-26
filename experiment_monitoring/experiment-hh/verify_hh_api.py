"""
verify_hh_api.py — Empirical verification of api.hh.ru claims.

Run from repo root:
    cd C:\\Users\\bhunp\\Documents\\auto-monitor-ml-cv\\repos\\Atomic-Scraper-Service
    uv run python experiment-hh\\verify_hh_api.py

Saves JSON samples to experiment-hh/samples/.
Prints a structured verification report to stdout.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make experiment-hh importable when run from repo root
sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import ProxyRotatingClient

BASE = "https://api.hh.ru"
SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)

# Moscow area code
AREA_MOSCOW = "1"
AREA_SPB = "2"


def save_sample(name: str, data: dict | list) -> Path:
    path = SAMPLES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> saved sample: {path.name}")
    return path


def trim_text(obj: dict, fields: list[str], max_len: int = 300) -> dict:
    """Return a shallow copy with long string fields trimmed."""
    out = dict(obj)
    for f in fields:
        if f in out and isinstance(out[f], str) and len(out[f]) > max_len:
            out[f] = out[f][:max_len] + "…[trimmed]"
    return out


# ---------------------------------------------------------------------------
# Step 1: Anonymous vacancy search
# ---------------------------------------------------------------------------

def test_vacancy_search(client: ProxyRotatingClient) -> dict | None:
    print("\n=== TEST 1: Anonymous vacancy search ===")
    date_from = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )
    params = {
        "text": "computer vision",
        "area": AREA_MOSCOW,
        "per_page": 10,
        "page": 0,
        "date_from": date_from,
    }
    print(f"  GET {BASE}/vacancies  params={params}")
    resp = client.get(f"{BASE}/vacancies", params=params)
    print(f"  HTTP {resp.status_code}  Content-Type: {resp.headers.get('content-type')}")
    print(f"  Rate-limit headers: {dict((k,v) for k,v in resp.headers.items() if 'rate' in k.lower() or 'x-ratelimit' in k.lower() or 'retry' in k.lower())}")

    if resp.status_code != 200:
        print(f"  FAILED: {resp.text[:500]}")
        return None

    data = resp.json()
    found = data.get("found", "?")
    pages = data.get("pages", "?")
    per_page = data.get("per_page", "?")
    items = data.get("items", [])
    print(f"  found={found}  pages={pages}  per_page={per_page}  items_returned={len(items)}")

    if items:
        first = items[0]
        print(f"  First vacancy id={first.get('id')}  name={first.get('name')}")
        print(f"  Top-level fields in list item: {sorted(first.keys())}")
        save_sample("01_vacancy_search", {
            "found": found,
            "pages": pages,
            "per_page": per_page,
            "items_count": len(items),
            "first_item_fields": sorted(first.keys()),
            "sample_items": [trim_text(v, ["description"], 200) for v in items[:3]],
        })
    return data


# ---------------------------------------------------------------------------
# Step 2: order_by=publication_time
# ---------------------------------------------------------------------------

def test_order_by(client: ProxyRotatingClient) -> None:
    print("\n=== TEST 2: order_by=publication_time ===")
    params = {
        "text": "machine learning",
        "area": AREA_MOSCOW,
        "per_page": 10,
        "page": 0,
        "order_by": "publication_time",
    }
    resp = client.get(f"{BASE}/vacancies", params=params)
    print(f"  HTTP {resp.status_code}")
    if resp.status_code == 400:
        err = resp.json()
        print(f"  FAILED (400): {err}")
        save_sample("02_order_by_publication_time_error", err)
        return
    if resp.status_code != 200:
        print(f"  FAILED ({resp.status_code}): {resp.text[:300]}")
        return

    data = resp.json()
    items = data.get("items", [])
    dates = [v.get("published_at") for v in items[:5]]
    print(f"  OK — first 5 published_at: {dates}")

    # Check if they are descending (newest first)
    if len(dates) >= 2:
        sorted_desc = sorted([d for d in dates if d], reverse=True)
        is_sorted = [d for d in dates if d] == sorted_desc
        print(f"  Sorted descending? {is_sorted}")

    save_sample("02_order_by_publication_time", {
        "status": resp.status_code,
        "found": data.get("found"),
        "sample_published_at": dates,
    })

    # Also test order_by=created_at for comparison
    params2 = dict(params)
    params2["order_by"] = "created_at"
    resp2 = client.get(f"{BASE}/vacancies", params=params2)
    print(f"  order_by=created_at → HTTP {resp2.status_code}")

    # Try listing valid order_by values via dictionaries
    print("  Checking /dictionaries for valid order_by values...")
    resp_dict = client.get(f"{BASE}/dictionaries")
    if resp_dict.status_code == 200:
        dicts = resp_dict.json()
        vacancy_search_order = dicts.get("vacancy_search_order", [])
        print(f"  valid order_by values: {[v.get('id') for v in vacancy_search_order]}")
        save_sample("02b_vacancy_search_order_values", vacancy_search_order)
    else:
        print(f"  /dictionaries failed: {resp_dict.status_code}")


# ---------------------------------------------------------------------------
# Step 3: GET /vacancies/{id} — full field set
# ---------------------------------------------------------------------------

def test_single_vacancy(client: ProxyRotatingClient, vacancy_id: str) -> None:
    print(f"\n=== TEST 3: GET /vacancies/{vacancy_id} ===")
    resp = client.get(f"{BASE}/vacancies/{vacancy_id}")
    print(f"  HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAILED: {resp.text[:300]}")
        return

    data = resp.json()
    top_fields = sorted(data.keys())
    print(f"  Top-level fields: {top_fields}")

    # Key fields of interest
    for field in ["description", "key_skills", "schedule", "experience",
                  "contacts", "working_days", "working_time_intervals",
                  "salary", "area", "employer", "type", "archived",
                  "has_test", "premium", "professional_roles"]:
        val = data.get(field)
        if val is None:
            print(f"  {field}: ABSENT")
        elif isinstance(val, str):
            print(f"  {field}: present, len={len(val)}")
        elif isinstance(val, list):
            print(f"  {field}: list len={len(val)}, sample={val[:2]}")
        else:
            print(f"  {field}: {val}")

    trimmed = trim_text(data, ["description"], 500)
    save_sample(f"03_vacancy_{vacancy_id}", trimmed)


# ---------------------------------------------------------------------------
# Step 4: GET /employers/{id}
# ---------------------------------------------------------------------------

def test_employer(client: ProxyRotatingClient, employer_id: str) -> None:
    print(f"\n=== TEST 4: GET /employers/{employer_id} ===")
    resp = client.get(f"{BASE}/employers/{employer_id}")
    print(f"  HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAILED: {resp.text[:300]}")
        return

    data = resp.json()
    print(f"  Top-level fields: {sorted(data.keys())}")
    for field in ["id", "name", "full_name", "area", "logo_urls",
                  "alternate_url", "description", "type", "open_vacancies",
                  "contacts"]:
        val = data.get(field)
        if val is not None:
            print(f"  {field}: {str(val)[:100]}")
        else:
            print(f"  {field}: ABSENT")

    trimmed = trim_text(data, ["description"], 300)
    save_sample(f"04_employer_{employer_id}", trimmed)

    # Test change_after parameter
    print("  Testing change_after parameter...")
    resp2 = client.get(f"{BASE}/employers/{employer_id}",
                       params={"change_after": "2020-01-01"})
    print(f"  /employers/{employer_id}?change_after=2020-01-01 → HTTP {resp2.status_code}")


# ---------------------------------------------------------------------------
# Step 5: Rate limit observation
# ---------------------------------------------------------------------------

def test_rate_limits(client: ProxyRotatingClient) -> None:
    print("\n=== TEST 5: Rate limit observation (5 rapid requests) ===")
    statuses = []
    for i in range(5):
        resp = client.get(f"{BASE}/vacancies", params={"text": "python", "per_page": 5})
        statuses.append(resp.status_code)
        rl_headers = {k: v for k, v in resp.headers.items()
                      if any(x in k.lower() for x in ["rate", "retry", "x-ratelimit", "limit"])}
        print(f"  Request {i+1}: HTTP {resp.status_code}  rl_headers={rl_headers}")
        time.sleep(0.3)

    save_sample("05_rate_limit_observation", {
        "statuses": statuses,
        "note": "5 requests with 0.3s delay between them",
    })


# ---------------------------------------------------------------------------
# Bonus: professional_roles for ML
# ---------------------------------------------------------------------------

def test_professional_roles(client: ProxyRotatingClient) -> None:
    print("\n=== BONUS: GET /professional_roles ===")
    resp = client.get(f"{BASE}/professional_roles")
    print(f"  HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"  FAILED: {resp.text[:200]}")
        return

    data = resp.json()
    # Flatten categories
    roles = []
    for cat in data.get("categories", []):
        for role in cat.get("roles", []):
            roles.append({"id": role["id"], "name": role["name"], "category": cat.get("name")})

    # Find ML-relevant roles
    ml_keywords = {"ml", "machine", "learning", "vision", "data", "analyst",
                   "нейрон", "данных", "машин", "глубок", "компьютерн"}
    ml_roles = [r for r in roles if any(kw in r["name"].lower() for kw in ml_keywords)]
    print(f"  Total roles: {len(roles)}")
    print(f"  ML-relevant roles:")
    for r in ml_roles:
        line = f"    id={r['id']}  name={r['name']}  cat={r['category']}"
        print(line.encode("utf-8", errors="replace").decode("utf-8"))

    save_sample("06_professional_roles_ml", {
        "total_roles": len(roles),
        "ml_relevant": ml_roles,
    })


# ---------------------------------------------------------------------------
# Bonus: RSS check
# ---------------------------------------------------------------------------

def test_rss(client: ProxyRotatingClient) -> None:
    print("\n=== BONUS: RSS feed check ===")
    url = "https://hh.ru/search/vacancy/rss"
    params = {"text": "machine learning", "area": AREA_MOSCOW}
    resp = client.get(url, params=params)
    print(f"  HTTP {resp.status_code}  Content-Type: {resp.headers.get('content-type')}")
    if resp.status_code == 200:
        snippet = resp.text[:500]
        is_xml = "<?xml" in snippet or "<rss" in snippet or "<feed" in snippet
        print(f"  Looks like XML/RSS: {is_xml}")
        print(f"  First 300 chars: {snippet[:300]}")
        save_sample("07_rss_check", {"status": 200, "content_type": resp.headers.get("content-type"), "snippet": snippet[:500]})
    else:
        print(f"  Response: {resp.text[:300]}")
        save_sample("07_rss_check", {"status": resp.status_code, "body": resp.text[:300]})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("hh.ru API Verification — anonymous, via RU rotating proxies")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    client = ProxyRotatingClient(max_retries=15, timeout=25.0)
    print(f"Loaded {len(client._proxies)} proxies, shuffled.")

    # Step 1: search
    search_data = test_vacancy_search(client)

    # Extract ids from search results for steps 3 & 4
    vacancy_id = None
    employer_id = None
    if search_data and search_data.get("items"):
        first = search_data["items"][0]
        vacancy_id = first.get("id")
        emp = first.get("employer") or {}
        employer_id = emp.get("id")
        print(f"\n  Using vacancy_id={vacancy_id}, employer_id={employer_id} for steps 3+4")

    # Step 2: order_by
    test_order_by(client)

    # Step 3: single vacancy
    if vacancy_id:
        test_single_vacancy(client, str(vacancy_id))

    # Step 4: employer
    if employer_id:
        test_employer(client, str(employer_id))

    # Step 5: rate limits
    test_rate_limits(client)

    # Bonus: professional_roles
    test_professional_roles(client)

    # Bonus: RSS
    test_rss(client)

    print("\n" + "=" * 60)
    print("Verification complete. Samples saved to experiment-hh/samples/")
    print("=" * 60)


if __name__ == "__main__":
    main()
