"""Аналитика результатов грид-парсинга Яндекс.Карт.

Считает:
  * сколько организаций вернул API всего (до дедупликации),
  * сколько уникальных по oid (без фильтра по радиусу),
  * сколько уникальных в радиусе 2500 м (итог),
  * плотность находок на ячейку в начале и в конце поиска
    (батчами по 10 запросов; точки сетки отсортированы от центра наружу).

Строит график (PNG) и печатает сводку.

Запуск:  PYTHONIOENCODING=utf-8 python 03_analytics.py
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── те же параметры, что в 01_scrape_yandex.py ──────────────────────────────
CENTER_LAT = 59.914403
CENTER_LON = 30.327319
RADIUS_M = 2500.0
GRID_STEP_M = 200.0
GRID_OVERLAP_M = 20.0
EFFECTIVE_STEP_M = GRID_STEP_M - GRID_OVERLAP_M

CATEGORIES = [
    "кафе", "ресторан", "бар", "продуктовый магазин", "магазин", "аптека",
    "салон красоты", "парикмахерская", "стоматология", "клиника", "автосервис",
    "фитнес", "банк", "химчистка", "ателье", "школа", "детский сад",
    "юридические услуги", "ремонт техники", "типография", "ветеринарная клиника",
    "автомойка", "цветы", "пекарня", "суши",
]

BATCH_SIZE = 10

DATA_DIR = Path(__file__).parent / "data"
RAW_GRID_DIR = DATA_DIR / "raw_grid"
OUT_DIR = Path(__file__).parent / "analytics_out"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def generate_grid_points(center_lat, center_lon, radius_m, step_m):
    lat_step = step_m / 111320.0
    lon_step = step_m / (111320.0 * math.cos(math.radians(center_lat)))
    n_steps = math.ceil(radius_m / step_m) + 1
    points = []
    for i in range(-n_steps, n_steps + 1):
        for j in range(-n_steps, n_steps + 1):
            lat = center_lat + i * lat_step
            lon = center_lon + j * lon_step
            if haversine_m(center_lat, center_lon, lat, lon) <= radius_m:
                points.append((lat, lon))
    points.sort(key=lambda p: haversine_m(center_lat, center_lon, p[0], p[1]))
    return points


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid_points = generate_grid_points(CENTER_LAT, CENTER_LON, RADIUS_M, EFFECTIVE_STEP_M)
    n_grid = len(grid_points)

    # ── Проход по всем вызовам в порядке их совершения ─────────────────────
    per_call_total = []        # сколько орг вернул API на каждый вызов
    per_call_inradius = []     # из них в радиусе
    per_call_dist = []         # расстояние ячейки от центра
    per_call_ok = []           # 1 — вызов успешный, 0 — ошибка
    seen_oids = set()          # уникальные (любые)
    seen_oids_radius = set()   # уникальные в радиусе
    per_call_new_radius = []   # новые уникальные-в-радиусе на вызов
    total_instances = 0
    missing_files = 0
    n_ok = n_err = 0
    err_kinds = Counter()      # тип ошибки

    def classify_error(payload) -> str:
        e = str(payload.get("error") or "")
        if "ERR_PROXY_AUTH_UNSUPPORTED" in e:
            return "proxy_auth"
        if "Timeout" in e or "ERR_TIMED_OUT" in e:
            return "timeout"
        if "ERR_TUNNEL_CONNECTION_FAILED" in e:
            return "tunnel_failed"
        if "captcha" in e.lower():
            return "captcha"
        return "other"

    for g_idx, (g_lat, g_lon) in enumerate(grid_points):
        cell_dist = haversine_m(CENTER_LAT, CENTER_LON, g_lat, g_lon)
        for cat in CATEGORIES:
            slug = cat.replace(" ", "_")
            path = RAW_GRID_DIR / f"g{g_idx:05d}_{slug}.json"
            orgs = []
            ok = 0
            payload = {}
            if path.exists():
                try:
                    payload = json.load(path.open(encoding="utf-8"))
                    orgs = payload.get("organizations") or []
                except Exception:
                    payload = {"error": "parse_fail"}
            else:
                missing_files += 1
                payload = {"error": "missing_file"}

            if payload.get("error"):
                n_err += 1
                err_kinds[classify_error(payload)] += 1
            else:
                n_ok += 1
                ok = 1
            per_call_ok.append(ok)

            n_total = len(orgs)
            n_inrad = 0
            n_new_rad = 0
            for org in orgs:
                oid = org.get("oid")
                if oid:
                    seen_oids.add(oid)
                coords = org.get("coordinates") or {}
                olat, olon = coords.get("lat"), coords.get("lon")
                if olat is None or olon is None:
                    continue
                if haversine_m(CENTER_LAT, CENTER_LON, olat, olon) <= RADIUS_M:
                    n_inrad += 1
                    if oid and oid not in seen_oids_radius:
                        seen_oids_radius.add(oid)
                        n_new_rad += 1

            total_instances += n_total
            per_call_total.append(n_total)
            per_call_inradius.append(n_inrad)
            per_call_dist.append(cell_dist)
            per_call_new_radius.append(n_new_rad)

    n_calls = len(per_call_total)

    # ── Сводные числа ──────────────────────────────────────────────────────
    print("=" * 70)
    print("СВОДКА")
    print("=" * 70)
    print(f"Точек сетки:                       {n_grid}")
    print(f"Категорий:                         {len(CATEGORIES)}")
    print(f"Всего вызовов API:                 {n_calls}")
    if missing_files:
        print(f"  (отсутствующих файлов кэша:      {missing_files})")
    print()
    print(f"Успешных вызовов:                  {n_ok}  ({100*n_ok/max(1,n_calls):.1f}%)")
    print(f"Вызовов с ошибкой:                 {n_err}  ({100*n_err/max(1,n_calls):.1f}%)")
    for kind, cnt in err_kinds.most_common():
        print(f"    {kind:14s} {cnt:6d}")
    print()
    print("!!! ВНИМАНИЕ: подавляющее большинство вызовов упало на ошибке прокси.")
    print("    Реально отработали только центральные ячейки сетки; остальные")
    print("    мгновенно возвращали ошибку (потому парсинг и шёл ~1с/вызов).")
    print()
    print(f"Орг-экземпляров возвращено API:    {total_instances}   (с дублями, до дедупа)")
    print(f"Уникальных по oid (без радиуса):   {len(seen_oids)}")
    print(f"Уникальных по oid в радиусе {RADIUS_M:.0f}м: {len(seen_oids_radius)}   (ИТОГ)")
    print()
    dup_dropped = total_instances - len(seen_oids)
    out_radius = len(seen_oids) - len(seen_oids_radius)
    print(f"Отброшено дубликатов:              {dup_dropped}  "
          f"({100*dup_dropped/max(1,total_instances):.1f}% от всех экземпляров)")
    print(f"Отброшено вне радиуса:             {out_radius}")
    print(f"Коэф. перекрытия (экз./уник.):     {total_instances/max(1,len(seen_oids_radius)):.2f}x")

    # ── Батчи по 10 вызовов ────────────────────────────────────────────────
    n_batches = math.ceil(n_calls / BATCH_SIZE)
    batch_idx = list(range(n_batches))
    batch_total = []      # сумма орг (с дублями) за батч
    batch_inrad = []      # сумма в радиусе
    batch_new = []        # новые уникальные за батч
    batch_dist = []       # средняя дистанция ячеек батча
    batch_ok = []         # успешных вызовов в батче (из 10)
    for b in range(n_batches):
        s = slice(b * BATCH_SIZE, (b + 1) * BATCH_SIZE)
        batch_total.append(sum(per_call_total[s]))
        batch_inrad.append(sum(per_call_inradius[s]))
        batch_new.append(sum(per_call_new_radius[s]))
        batch_ok.append(sum(per_call_ok[s]))
        seg = per_call_dist[s]
        batch_dist.append(sum(seg) / len(seg) if seg else 0)

    # средняя плотность на ячейку (вызов) в начале/конце
    first10 = per_call_inradius[:10 * BATCH_SIZE]   # первые 10 батчей = 100 вызовов
    last10 = per_call_inradius[-10 * BATCH_SIZE:]
    print()
    print("ПЛОТНОСТЬ НА ВЫЗОВ (орг в радиусе на 1 запрос):")
    print(f"  начало поиска (центр, 1-й батч):   {batch_inrad[0]/BATCH_SIZE:.2f} орг/вызов")
    print(f"  начало (первые 100 вызовов):       {sum(first10)/len(first10):.2f} орг/вызов")
    print(f"  конец  (последние 100 вызовов):    {sum(last10)/len(last10):.2f} орг/вызов")
    print(f"  конец поиска (последний батч):     {batch_inrad[-1]/BATCH_SIZE:.2f} орг/вызов")
    print("=" * 70)

    # граница, после которой пошли сплошные ошибки прокси
    last_ok_batch = max((i for i, v in enumerate(batch_ok) if v > 0), default=0)

    # ── График ─────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(3, 1, figsize=(14, 13), sharex=True)

    axe = axes[0]
    axe.bar(batch_idx, batch_ok, width=1.0, color="#2a6", label="успешных вызовов (из 10)")
    axe.bar(batch_idx, [BATCH_SIZE - v for v in batch_ok], width=1.0, bottom=batch_ok,
            color="#d66", label="ошибок прокси (из 10)")
    axe.axvline(last_ok_batch + 0.5, color="#000", lw=1, ls=":")
    axe.set_ylabel("вызовов в батче")
    axe.set_title(f"Успех/ошибка по батчам — прокси отвалился после батча ~{last_ok_batch} "
                  f"(вызов ~{(last_ok_batch+1)*BATCH_SIZE})")
    axe.legend(loc="center right")
    axe.grid(True, alpha=0.3)

    ax = axes[1]
    ax.bar(batch_idx, batch_total, width=1.0, color="#bcd", label="возвращено API (с дублями)")
    ax.bar(batch_idx, batch_inrad, width=1.0, color="#2a6", label="в радиусе 2500 м")
    ax.plot(batch_idx, batch_new, color="#c33", lw=1.3, label="новые уникальные")
    ax.set_ylabel("организаций за батч (10 запросов)")
    ax.set_title("Плотность находок по ходу поиска\n"
                 "(точки сетки отсортированы от центра наружу → слева центр, справа край)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    ax2 = axes[2]
    cum_new = []
    acc = 0
    for v in batch_new:
        acc += v
        cum_new.append(acc)
    ax2.plot(batch_idx, cum_new, color="#c33", lw=2, label="накопл. уникальных в радиусе")
    ax2.set_ylabel("накопленные уникальные орг", color="#c33")
    ax2.tick_params(axis="y", labelcolor="#c33")
    axd = ax2.twinx()
    axd.plot(batch_idx, batch_dist, color="#39c", lw=1.5, ls="--",
             label="ср. расстояние ячейки от центра, м")
    axd.set_ylabel("расстояние от центра, м", color="#39c")
    axd.tick_params(axis="y", labelcolor="#39c")
    ax2.set_xlabel("номер батча (× 10 запросов)")
    ax2.set_title("Накопление уникальных организаций vs удаление от центра")
    ax2.grid(True, alpha=0.3)
    lines1, lab1 = ax2.get_legend_handles_labels()
    lines2, lab2 = axd.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, lab1 + lab2, loc="center right")

    fig.tight_layout()
    chart_path = OUT_DIR / "density_over_search.png"
    fig.savefig(chart_path, dpi=120)
    print(f"[+] График: {chart_path}")

    # сохраним числовую сводку
    summary = {
        "grid_points": n_grid,
        "categories": len(CATEGORIES),
        "api_calls": n_calls,
        "calls_ok": n_ok,
        "calls_error": n_err,
        "error_kinds": dict(err_kinds),
        "last_successful_batch": last_ok_batch,
        "org_instances_returned": total_instances,
        "unique_by_oid_all": len(seen_oids),
        "unique_by_oid_in_radius": len(seen_oids_radius),
        "duplicates_dropped": dup_dropped,
        "out_of_radius_dropped": out_radius,
        "overlap_factor": round(total_instances / max(1, len(seen_oids_radius)), 3),
        "density_first_batch_per_call": round(batch_inrad[0] / BATCH_SIZE, 3),
        "density_first_100_per_call": round(sum(first10) / len(first10), 3),
        "density_last_100_per_call": round(sum(last10) / len(last10), 3),
        "batch_size": BATCH_SIZE,
        "batch_inradius": batch_inrad,
        "batch_total": batch_total,
        "batch_new_unique": batch_new,
        "batch_avg_dist_m": [round(d, 1) for d in batch_dist],
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[+] Числа: {OUT_DIR / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
