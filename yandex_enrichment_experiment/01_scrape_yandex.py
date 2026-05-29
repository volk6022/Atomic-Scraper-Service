"""Парсинг организаций Яндекс.Карт в радиусе вокруг точки.

Точка: 59°54'57"N 30°19'49"E = (59.91583, 30.33028)
Радиус: 2000 м

Идёт по списку категорий, собирает organizations, дедуплицирует по `oid`,
фильтрует по haversine distance ≤ радиуса.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_URL = "http://localhost:8000/api/v1/yandex-maps/extract"
API_KEY = "default_internal_key"

CENTER_LAT = 59.91583
CENTER_LON = 30.33028
RADIUS_M = 2500.0  # bumped from 2000 → ~600 unique orgs expected

# Широкий набор категорий для покрытия большинства организаций в районе.
# Дубликаты дедуплицируются по oid в финальном списке.
CATEGORIES = [
    "кафе",
    "ресторан",
    "бар",
    "продуктовый магазин",
    "магазин",
    "аптека",
    "салон красоты",
    "парикмахерская",
    "стоматология",
    "клиника",
    "автосервис",
    "фитнес",
    "банк",
    "химчистка",
    "ателье",
    "школа",
    "детский сад",
    "юридические услуги",
    "ремонт техники",
    "типография",
    "ветеринарная клиника",
    "автомойка",
    "цветы",
    "пекарня",
    "суши",
]

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
REVIEWS_DIR = DATA_DIR / "reviews"

REVIEWS_API_URL = "http://localhost:8000/api/v1/yandex-maps/reviews"
# Phase 6a: skip orgs with too few reviews — review collection is cheap but not
# free (one Chromium session per call); orgs with 0-1 reviews don't help signal.
REVIEWS_MIN_COUNT = 2
REVIEWS_PAGES = 1   # 1 page ~= up to 50 reviews; enough for "reviews_sample"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в метрах (формула гаверсинусов)."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_reviews_for_org(
    client: httpx.Client, oid: str, seoname: str, count: int = 50
) -> dict[str, Any]:
    """Fetch reviews for one org via /api/v1/yandex-maps/reviews.

    Returns the raw response dict; errors are returned as
    ``{"error": "...", "reviews": []}`` so caller can persist a sentinel and
    avoid re-attempting forever.
    """
    try:
        resp = client.post(
            REVIEWS_API_URL,
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={
                "business_oid": oid,
                "seoname": seoname,
                "count": count,
                "ranking": "by_time",
                "pages": REVIEWS_PAGES,
                "include_raw": False,
            },
            timeout=180.0,
        )
    except Exception as e:
        return {"error": str(e), "reviews": []}
    if resp.status_code != 200:
        return {"error": resp.text[:300], "status": resp.status_code, "reviews": []}
    return resp.json()


def collect_reviews_for_all(organizations: list[dict[str, Any]]) -> None:
    """For each org with sufficient review count, fetch and cache reviews.

    Idempotent — skips orgs whose JSON file already exists.
    """
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    total = len(organizations)
    collected = 0
    skipped_cached = 0
    skipped_few = 0
    failed = 0

    with httpx.Client() as client:
        for idx, org in enumerate(organizations, 1):
            oid = org.get("oid")
            seoname = org.get("seoname")
            title = org.get("title", "?")
            if not oid or not seoname:
                continue
            rcount = org.get("reviewsCount") or 0
            target_path = REVIEWS_DIR / f"{oid}.json"
            if target_path.exists():
                skipped_cached += 1
                continue
            if rcount < REVIEWS_MIN_COUNT:
                # write empty sentinel so we don't re-check
                with target_path.open("w", encoding="utf-8") as f:
                    json.dump(
                        {"oid": oid, "seoname": seoname, "skipped_low_count": True,
                         "reviewsCount": rcount, "reviews": []},
                        f, ensure_ascii=False, indent=2,
                    )
                skipped_few += 1
                continue
            print(f"  [{idx:3d}/{total}] reviews '{title[:40]}' (count~{rcount})...",
                  end=" ", flush=True)
            t0 = time.time()
            payload = fetch_reviews_for_org(client, oid, seoname)
            elapsed = time.time() - t0
            if payload.get("error"):
                print(f"FAIL ({elapsed:.1f}s): {payload['error'][:120]}")
                failed += 1
            else:
                print(f"got {len(payload.get('reviews', []))} in {elapsed:.1f}s")
                collected += 1
            with target_path.open("w", encoding="utf-8") as f:
                json.dump({"oid": oid, "seoname": seoname, **payload},
                          f, ensure_ascii=False, indent=2)

    print()
    print(f"[+] Reviews: collected={collected}, cached={skipped_cached}, "
          f"low-count-skipped={skipped_few}, failed={failed}")


def scrape_category(client: httpx.Client, query: str) -> dict[str, Any]:
    """Сделать один запрос к /extract."""
    resp = client.post(
        API_URL,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "query": query,
            "region_id": 2,
            "city_slug": "saint-petersburg",
            "target_count": 100,
            "include_raw": False,
        },
        timeout=180.0,
    )
    if resp.status_code != 200:
        return {"error": resp.text[:300], "status": resp.status_code, "organizations": []}
    return resp.json()


def main() -> int:
    import os

    # COLLECT_REVIEWS=1 → only run review collection over already-cached orgs.
    # COLLECT_REVIEWS=0 (default) → just (re)build organizations.json as before.
    # COLLECT_REVIEWS=both → do both (extract organizations, then collect reviews).
    mode = os.getenv("COLLECT_REVIEWS", "0").lower()
    reviews_only = mode in ("1", "only", "yes", "true")
    do_reviews = reviews_only or mode in ("both", "all")

    if reviews_only:
        # Load existing organizations.json and just collect reviews.
        out_path = DATA_DIR / "organizations.json"
        if not out_path.exists():
            print(f"[!] {out_path} missing — run with COLLECT_REVIEWS=0 first.")
            return 1
        with out_path.open("r", encoding="utf-8") as f:
            summary = json.load(f)
        organizations = summary.get("organizations", [])
        print(f"[*] Reviews-only mode: {len(organizations)} orgs from cache")
        collect_reviews_for_all(organizations)
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[*] Center: ({CENTER_LAT}, {CENTER_LON}) radius={RADIUS_M}m")
    print(f"[*] Categories: {len(CATEGORIES)}")
    print()

    all_orgs: dict[str, dict[str, Any]] = {}  # oid -> org

    with httpx.Client() as client:
        for idx, cat in enumerate(CATEGORIES, 1):
            slug = cat.replace(" ", "_")
            raw_path = RAW_DIR / f"{slug}.json"

            if raw_path.exists():
                print(f"[{idx:2d}/{len(CATEGORIES)}] {cat!r} — cached, loading")
                with raw_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
            else:
                print(f"[{idx:2d}/{len(CATEGORIES)}] {cat!r} — fetching...", end=" ", flush=True)
                t0 = time.time()
                try:
                    payload = scrape_category(client, cat)
                except Exception as e:
                    print(f"FAIL: {e}")
                    payload = {"error": str(e), "organizations": []}
                elapsed = time.time() - t0
                print(f"got {len(payload.get('organizations', []))} orgs in {elapsed:.1f}s")
                with raw_path.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

            for org in payload.get("organizations", []) or []:
                oid = org.get("oid")
                if not oid:
                    continue
                coords = org.get("coordinates")
                if not coords:
                    continue
                lat = coords.get("lat")
                lon = coords.get("lon")
                if lat is None or lon is None:
                    continue
                dist = haversine_m(CENTER_LAT, CENTER_LON, lat, lon)
                if dist > RADIUS_M:
                    continue
                if oid in all_orgs:
                    # уже есть; дополним категориями, если приехал из другого запроса
                    existing_cats = all_orgs[oid].get("_search_queries", [])
                    if cat not in existing_cats:
                        existing_cats.append(cat)
                        all_orgs[oid]["_search_queries"] = existing_cats
                    continue
                org["_distance_m"] = round(dist, 1)
                org["_search_queries"] = [cat]
                all_orgs[oid] = org

    # сохранить итог
    out_path = DATA_DIR / "organizations.json"
    organizations = sorted(all_orgs.values(), key=lambda o: o.get("_distance_m", 0))
    summary = {
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "radius_m": RADIUS_M,
        "categories_queried": CATEGORIES,
        "total_unique": len(organizations),
        "organizations": organizations,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print(f"[+] Done. Unique orgs in {RADIUS_M}m radius: {len(organizations)}")
    print(f"[+] Saved to: {out_path}")

    # топ-10 для отчёта
    print()
    print("Sample (first 10):")
    for o in organizations[:10]:
        cats = ", ".join(c.get("name", "?") for c in (o.get("categories") or [])[:2])
        print(f"  - {o['title'][:50]:50s} | {cats[:40]:40s} | {o.get('_distance_m'):.0f}m")

    if do_reviews:
        print()
        print("[*] COLLECT_REVIEWS=both — fetching reviews for each org...")
        collect_reviews_for_all(organizations)

    return 0


if __name__ == "__main__":
    sys.exit(main())
