"""Эксперимент 1 (БЕЗ трафика): оптимальный шаг сетки по реальным данным центра.

Идея: центральные 31 ячейка отсняты плотно (шаг 180 м, радиус кластера ~570 м) —
принимаем найденное там за «правду» (ground truth, GT) в пределах R_GT.

Считаем:
  1. r_catch для каждой орг — максимальное расстояние от орг до ll ячейки,
     которая её ВСЁ ЕЩЁ вернула. Чем больше — тем реже можно ставить сетку.
  2. recall vs шаг сетки: берём подрешётку точек (i%k==0, j%k==0), шаг = k·180 м,
     и считаем, какую долю GT мы бы поймали.
  3. Всё то же раздельно по категориям (плотные vs редкие).
  4. SSR-only (первые ~25 на запрос) vs полная выдача — оценка вклада пагинации.

Источник: yandex_enrichment_experiment/data/raw_grid/g000..g030_*.json
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[1]
RG = REPO / "yandex_enrichment_experiment" / "data" / "raw_grid"
OUT = Path(__file__).parent / "results"

CLAT, CLON = 59.914403, 30.327319
STEP = 180.0          # эффективный шаг базовой плотной сетки
R_GT = 300.0          # радиус «правды»: внутри кластер ячеек окружает орги со всех сторон
SSR_CAP = 25          # сколько орг считаем «бесплатной» SSR-страницей (без пагинации)


def hv(a, b, c, d):
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp = math.radians(c - a); dl = math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def build_grid():
    ls = STEP / 111320.0
    lo = STEP / (111320.0 * math.cos(math.radians(CLAT)))
    n = math.ceil(2500 / STEP) + 1
    pts = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            la = CLAT + i * ls; ln = CLON + j * lo
            if hv(CLAT, CLON, la, ln) <= 2500:
                pts.append((i, j, la, ln))
    pts.sort(key=lambda p: hv(CLAT, CLON, p[2], p[3]))
    return pts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pts = build_grid()

    # idx -> (i,j,lat,lon); только те, что есть в кэше
    cached_idx = sorted({int(f.name[1:6]) for f in RG.glob("g*.json")})
    print(f"Ячеек в кэше: {len(cached_idx)} (idx {cached_idx[0]}..{cached_idx[-1]})")
    cluster_r = max(hv(CLAT, CLON, pts[i][2], pts[i][3]) for i in cached_idx)
    print(f"Радиус кластера ячеек: {cluster_r:.0f} м;  R_GT={R_GT:.0f} м")

    # org_pos[oid] = (lat,lon,cat0)  ;  org_cells[oid] = list of (idx, ssr_rank)
    org_pos = {}
    org_cat = {}
    org_cells = defaultdict(list)        # oid -> [(idx, rank_in_query)]
    per_cat_counts = defaultdict(list)   # cat -> [n per query]

    for f in sorted(RG.glob("g*.json")):
        idx = int(f.name[1:6]); cat = f.name[7:-5]
        if idx not in cached_idx:
            continue
        try:
            p = json.load(f.open(encoding="utf-8"))
        except Exception:
            continue
        orgs = p.get("organizations") or []
        if not orgs:
            continue
        per_cat_counts[cat].append(len(orgs))
        for rank, o in enumerate(orgs):
            oid = o.get("oid"); c = o.get("coordinates") or {}
            if not oid or c.get("lat") is None:
                continue
            org_pos.setdefault(oid, (c["lat"], c["lon"]))
            org_cat.setdefault(oid, cat)
            org_cells[oid].append((idx, rank))

    # GT: орги в пределах R_GT от центра
    gt = {oid for oid, (la, ln) in org_pos.items() if hv(CLAT, CLON, la, ln) <= R_GT}
    print(f"GT организаций в радиусе {R_GT:.0f} м: {len(gt)}")

    # ── 1. r_catch: макс. расстояние орг до вернувшей её ячейки ───────────────
    r_catch = {}
    r_catch_ssr = {}     # то же, но только если орг попала в SSR-топ (rank<SSR_CAP)
    idx_ll = {i: (pts[i][2], pts[i][3]) for i in cached_idx}
    for oid in gt:
        la, ln = org_pos[oid]
        ds = [hv(la, ln, *idx_ll[idx]) for idx, _ in org_cells[oid]]
        r_catch[oid] = max(ds) if ds else 0
        ds_ssr = [hv(la, ln, *idx_ll[idx]) for idx, rk in org_cells[oid] if rk < SSR_CAP]
        if ds_ssr:
            r_catch_ssr[oid] = max(ds_ssr)

    rc = sorted(r_catch.values())
    print()
    print("=== r_catch (макс. расстояние до ячейки, которая всё ещё вернула орг) ===")
    print(f"  median={statistics.median(rc):.0f}  p75={rc[int(len(rc)*.75)]:.0f}  "
          f"p90={rc[int(len(rc)*.9)]:.0f}  max={rc[-1]:.0f} м")
    print("  → даже в нашем ограниченном кластере орги ловятся ячейками на таком удалении.")

    # ── 2. recall vs шаг сетки (подрешётка i%k==0, j%k==0) ────────────────────
    ij_of_idx = {i: (pts[i][0], pts[i][1]) for i in cached_idx}
    print()
    print("=== recall vs шаг сетки (GT центра) ===")
    spacings = []
    recalls = []
    recalls_ssr = []
    ncells_full_proj = []   # сколько ячеек дал бы такой шаг на весь круг 2500 м
    for k in range(1, 8):
        used = [i for i in cached_idx if ij_of_idx[i][0] % k == 0 and ij_of_idx[i][1] % k == 0]
        if not used:
            continue
        used_set = set(used)
        recovered = {oid for oid in gt if any(idx in used_set for idx, _ in org_cells[oid])}
        recovered_ssr = {oid for oid in gt
                         if any(idx in used_set and rk < SSR_CAP for idx, rk in org_cells[oid])}
        rec = 100 * len(recovered) / max(1, len(gt))
        rec_ssr = 100 * len(recovered_ssr) / max(1, len(gt))
        # проекция числа ячеек на весь круг 2500 м при шаге k*180
        eff = k * STEP
        proj = sum(1 for (i, j, la, ln) in pts
                   if (round((la - CLAT) * 111320.0 / eff)) is not None) if False else None
        # точная проекция: построить решётку с шагом eff
        ls = eff / 111320.0; lo = eff / (111320.0 * math.cos(math.radians(CLAT)))
        nn = math.ceil(2500 / eff) + 1
        proj = sum(1 for a in range(-nn, nn + 1) for b in range(-nn, nn + 1)
                   if hv(CLAT, CLON, CLAT + a * ls, CLON + b * lo) <= 2500)
        spacings.append(eff); recalls.append(rec); recalls_ssr.append(rec_ssr)
        ncells_full_proj.append(proj)
        print(f"  шаг {eff:5.0f} м (k={k}): recall_full={rec:5.1f}%  "
              f"recall_SSR_only={rec_ssr:5.1f}%  ячеек_на_круг≈{proj}")

    # ── 3. По категориям: плотность и потолок ─────────────────────────────────
    print()
    print("=== категории: ср/макс орг на запрос (виден ли потолок) ===")
    cat_rows = []
    for cat in sorted(per_cat_counts, key=lambda c: -max(per_cat_counts[c])):
        cs = per_cat_counts[cat]
        cat_rows.append((cat, statistics.mean(cs), max(cs)))
    for cat, mean, mx in cat_rows:
        flag = "  <- упирается в потолок" if mx >= 30 else ""
        print(f"  {cat:24s} ср={mean:4.1f} макс={mx:3d}{flag}")

    # ── Графики ───────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))

    a0 = ax[0]
    a0.plot(spacings, recalls, "o-", color="#2a6", lw=2, label="полная выдача")
    a0.plot(spacings, recalls_ssr, "s--", color="#39c", lw=2, label="только SSR (≤25, без скролла)")
    a0.axhline(95, color="#c33", ls=":", label="95%")
    a0.set_xlabel("шаг сетки, м"); a0.set_ylabel("recall от GT центра, %")
    a0.set_title("Полнота охвата vs шаг сетки\n(GT = плотно отснятый центр)")
    a0.grid(alpha=.3); a0.legend()
    for x, y, n in zip(spacings, recalls, ncells_full_proj):
        a0.annotate(f"{n} яч.", (x, y), textcoords="offset points", xytext=(0, 8),
                    fontsize=8, ha="center", color="#555")

    a1 = ax[1]
    a1.hist(rc, bins=20, color="#2a6", alpha=.8)
    a1.axvline(statistics.median(rc), color="#c33", ls="--",
               label=f"median {statistics.median(rc):.0f} м")
    a1.set_xlabel("r_catch, м"); a1.set_ylabel("организаций")
    a1.set_title("На каком удалении ячейки орг ещё ловится\n(больше → реже можно ставить сетку)")
    a1.grid(alpha=.3); a1.legend()

    fig.tight_layout()
    p = OUT / "01_grid_resolution.png"
    fig.savefig(p, dpi=120)
    print(f"\n[+] График: {p}")

    json.dump({
        "R_GT": R_GT, "gt_count": len(gt), "cluster_radius_m": round(cluster_r),
        "orgs_per_query_median": statistics.median([x for v in per_cat_counts.values() for x in v]),
        "r_catch_median_m": round(statistics.median(rc)),
        "r_catch_p90_m": round(rc[int(len(rc) * .9)]),
        "spacing_m": spacings, "recall_full_pct": recalls, "recall_ssr_pct": recalls_ssr,
        "projected_cells_2500m": ncells_full_proj,
        "category_mean_max": {c: [round(m, 1), mx] for c, m, mx in cat_rows},
    }, (OUT / "01_grid_sim.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[+] Числа: {OUT / '01_grid_sim.json'}")


if __name__ == "__main__":
    main()
