"""Парсинг организаций Яндекс.Карт сеткой вокруг заданной точки.

Точка: 59.914403, 30.327319
Радиус: 2500 м
Сетка: шаг 200 м, нахлёст 20 м → эффективный шаг 180 м

Для каждой ячейки сетки × каждой категории делается запрос к API
с ll={lon},{lat}&z=17, что фокусирует поиск на данной ячейке.
Результаты дедуплицируются по oid и фильтруются haversine ≤ 2500 м.

Кэш: data/raw_grid/g{idx:05d}_{category}.json — скрипт можно прерывать
и запускать заново, уже обработанные ячейки пропускаются.
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

CENTER_LAT = 59.914403
CENTER_LON = 30.327319
RADIUS_M = 2500.0

GRID_STEP_M = 200.0      # размер ячейки сетки, метры
GRID_OVERLAP_M = 20.0    # нахлёст между соседними ячейками, метры
EFFECTIVE_STEP_M = GRID_STEP_M - GRID_OVERLAP_M  # = 180 м

# target_count меньше 100 — ищем в малой области, >30 орг на ячейку редко
GRID_TARGET_COUNT = 30

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
RAW_GRID_DIR = DATA_DIR / "raw_grid"

REVIEWS_DIR = DATA_DIR / "reviews"
REVIEWS_API_URL = "http://localhost:8000/api/v1/yandex-maps/reviews"
REVIEWS_MIN_COUNT = 2
REVIEWS_PAGES = 1


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в метрах (формула гаверсинусов)."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def generate_grid_points(
    center_lat: float, center_lon: float, radius_m: float, step_m: float
) -> list[tuple[float, float]]:
    """Вернуть точки регулярной сетки внутри круга заданного радиуса.

    Шаг задаётся в метрах и переводится в градусы с учётом широты центра.
    Точки сортируются по расстоянию от центра (ближние обрабатываются первыми).
    """
    lat_step = step_m / 111320.0
    lon_step = step_m / (111320.0 * math.cos(math.radians(center_lat)))

    n_steps = math.ceil(radius_m / step_m) + 1

    points: list[tuple[float, float]] = []
    for i in range(-n_steps, n_steps + 1):
        for j in range(-n_steps, n_steps + 1):
            lat = center_lat + i * lat_step
            lon = center_lon + j * lon_step
            if haversine_m(center_lat, center_lon, lat, lon) <= radius_m:
                points.append((lat, lon))

    points.sort(key=lambda p: haversine_m(center_lat, center_lon, p[0], p[1]))
    return points


def scrape_grid_cell(
    client: httpx.Client, query: str, lat: float, lon: float
) -> dict[str, Any]:
    """Запрос к /extract с географической привязкой (ll=lon,lat&z=17)."""
    resp = client.post(
        API_URL,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "query": query,
            "region_id": 2,
            "city_slug": "saint-petersburg",
            "target_count": GRID_TARGET_COUNT,
            "include_raw": False,
            "ll_lat": lat,
            "ll_lon": lon,
        },
        timeout=180.0,
    )
    if resp.status_code != 200:
        return {"error": resp.text[:300], "status": resp.status_code, "organizations": []}
    return resp.json()


def fetch_reviews_for_org(
    client: httpx.Client, oid: str, seoname: str
) -> dict[str, Any]:
    try:
        resp = client.post(
            REVIEWS_API_URL,
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={
                "business_oid": oid,
                "seoname": seoname,
                "count": 50,
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
    """Сбор отзывов для всех организаций. Идемпотентен."""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    total = len(organizations)
    collected = skipped_cached = skipped_few = failed = 0

    with httpx.Client() as client:
        for idx, org in enumerate(organizations, 1):
            oid = org.get("oid")
            seoname = org.get("seoname")
            if not oid or not seoname:
                continue
            rcount = org.get("reviewsCount") or 0
            target_path = REVIEWS_DIR / f"{oid}.json"
            if target_path.exists():
                skipped_cached += 1
                continue
            if rcount < REVIEWS_MIN_COUNT:
                with target_path.open("w", encoding="utf-8") as f:
                    json.dump(
                        {"oid": oid, "seoname": seoname, "skipped_low_count": True,
                         "reviewsCount": rcount, "reviews": []},
                        f, ensure_ascii=False, indent=2,
                    )
                skipped_few += 1
                continue
            print(
                f"  [{idx:3d}/{total}] reviews '{org.get('title', '?')[:40]}' "
                f"(count~{rcount})...",
                end=" ", flush=True,
            )
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
    print(f"[+] Отзывы: собрано={collected}, кэш={skipped_cached}, "
          f"мало отзывов={skipped_few}, ошибки={failed}")


def main() -> int:
    import os

    mode = os.getenv("COLLECT_REVIEWS", "0").lower()
    reviews_only = mode in ("1", "only", "yes", "true")
    do_reviews = reviews_only or mode in ("both", "all")

    if reviews_only:
        out_path = DATA_DIR / "organizations.json"
        if not out_path.exists():
            print(f"[!] {out_path} missing — сначала запустите без COLLECT_REVIEWS")
            return 1
        with out_path.open("r", encoding="utf-8") as f:
            summary = json.load(f)
        organizations = summary.get("organizations", [])
        print(f"[*] Режим отзывов: {len(organizations)} орг из кэша")
        collect_reviews_for_all(organizations)
        return 0

    # ── Генерация сетки ───────────────────────────────────────────────────────
    grid_points = generate_grid_points(CENTER_LAT, CENTER_LON, RADIUS_M, EFFECTIVE_STEP_M)

    total_calls = len(grid_points) * len(CATEGORIES)
    est_hours = total_calls * 30 / 3600

    print(f"[*] Центр: ({CENTER_LAT}, {CENTER_LON}), радиус={RADIUS_M:.0f}м")
    print(f"[*] Сетка: шаг={GRID_STEP_M:.0f}м, нахлёст={GRID_OVERLAP_M:.0f}м "
          f"→ эффективный шаг={EFFECTIVE_STEP_M:.0f}м")
    print(f"[*] Точек в сетке: {len(grid_points)}")
    print(f"[*] Категорий: {len(CATEGORIES)}")
    print(f"[*] Всего запросов: {total_calls}")
    print(f"[*] Оценка времени (~30с/запрос): {est_hours:.1f}ч")
    print()

    RAW_GRID_DIR.mkdir(parents=True, exist_ok=True)

    all_orgs: dict[str, dict[str, Any]] = {}
    call_idx = 0
    cached_count = 0
    t_start = time.time()

    with httpx.Client() as client:
        for g_idx, (g_lat, g_lon) in enumerate(grid_points):
            for cat in CATEGORIES:
                call_idx += 1
                slug = cat.replace(" ", "_")
                cache_path = RAW_GRID_DIR / f"g{g_idx:05d}_{slug}.json"

                if cache_path.exists():
                    with cache_path.open("r", encoding="utf-8") as f:
                        payload = json.load(f)
                    cached_count += 1
                else:
                    # ETA на основе реально сделанных запросов
                    done_live = call_idx - cached_count
                    eta_str = ""
                    if done_live > 1:
                        elapsed_total = time.time() - t_start
                        rate = elapsed_total / done_live
                        remaining = total_calls - call_idx
                        eta_h = remaining * rate / 3600
                        eta_str = f" ETA≈{eta_h:.1f}ч"

                    print(
                        f"[{call_idx:6d}/{total_calls}] g{g_idx:05d} "
                        f"({g_lat:.5f},{g_lon:.5f}) {cat!r}...{eta_str}",
                        end=" ", flush=True,
                    )
                    t0 = time.time()
                    try:
                        payload = scrape_grid_cell(client, cat, g_lat, g_lon)
                    except Exception as e:
                        print(f"FAIL: {e}")
                        payload = {"error": str(e), "organizations": []}
                    elapsed = time.time() - t0
                    n = len(payload.get("organizations", []) or [])
                    print(f"got {n} in {elapsed:.1f}с")

                    with cache_path.open("w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)

                # Агрегация
                for org in payload.get("organizations", []) or []:
                    oid = org.get("oid")
                    if not oid:
                        continue
                    coords = org.get("coordinates") or {}
                    olat = coords.get("lat")
                    olon = coords.get("lon")
                    if olat is None or olon is None:
                        continue
                    dist = haversine_m(CENTER_LAT, CENTER_LON, olat, olon)
                    if dist > RADIUS_M:
                        continue
                    if oid not in all_orgs:
                        org["_distance_m"] = round(dist, 1)
                        org["_grid_point"] = [g_idx, round(g_lat, 6), round(g_lon, 6)]
                        org["_search_queries"] = [cat]
                        all_orgs[oid] = org
                    else:
                        sq = all_orgs[oid].setdefault("_search_queries", [])
                        if cat not in sq:
                            sq.append(cat)

    # ── Сохранение итога ─────────────────────────────────────────────────────
    organizations = sorted(all_orgs.values(), key=lambda o: o.get("_distance_m", 0))
    summary = {
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "radius_m": RADIUS_M,
        "grid_step_m": GRID_STEP_M,
        "grid_overlap_m": GRID_OVERLAP_M,
        "effective_step_m": EFFECTIVE_STEP_M,
        "grid_points_total": len(grid_points),
        "categories_queried": CATEGORIES,
        "total_unique": len(organizations),
        "organizations": organizations,
    }
    out_path = DATA_DIR / "organizations.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - t_start
    print()
    print(f"[+] Готово. Уникальных орг в {RADIUS_M:.0f}м: {len(organizations)}")
    print(f"[+] Время: {total_elapsed / 3600:.2f}ч")
    print(f"[+] Сохранено: {out_path}")
    print()
    print("Первые 10:")
    for o in organizations[:10]:
        cats = ", ".join(c.get("name", "?") for c in (o.get("categories") or [])[:2])
        print(f"  - {o['title'][:50]:50s} | {cats[:40]:40s} | {o.get('_distance_m'):.0f}м")

    if do_reviews:
        print()
        print("[*] COLLECT_REVIEWS=both — собираем отзывы...")
        collect_reviews_for_all(organizations)

    return 0


if __name__ == "__main__":
    sys.exit(main())
