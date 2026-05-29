"""Дедупликация organizations.json.

Стратегия:
1. Группируем по нормализованному title (lowercase, без знаков препинания, пробелов).
2. В каждой группе берём представителя — ближайшую к центру организацию.
3. Generic-имена ("магазин продуктов", "цветы", "автомойка", "ателье", без названия)
   группируем по (нормализованный title + first category). Иначе по 50 "Магазин
   продуктов" мы прогоним 50 одинаковых research'ей.
4. Сохраняем `organizations_dedup.json` со списком уникальных представителей +
   `duplicates` — сколько слилось в группу (для статистики).

В research-агент пойдут уникальные представители.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA_DIR = Path(__file__).parent / "data"
IN_PATH = DATA_DIR / "organizations.json"
OUT_PATH = DATA_DIR / "organizations_dedup.json"

# Имена-маркеры, которые не уникальны без бренда.
GENERIC_TITLE_PATTERNS = [
    r"^магазин",
    r"^продуктовый",
    r"^продукты",
    r"^цветы",
    r"^автомойка",
    r"^ателье",
    r"^парикмахерская",
    r"^аптека",
    r"^кафе",
    r"^бар",
    r"^салон красоты",
    r"^салон",
    r"^ремонт",
    r"^детский сад",
    r"^школа",
    r"^общеобразовательная",
    r"^средняя общеобразовательная школа",
]


def normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[«»\"'`(),.\-—–_]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_generic(title_norm: str) -> bool:
    return any(re.match(p, title_norm) for p in GENERIC_TITLE_PATTERNS)


def group_key(org: dict[str, Any]) -> str:
    title = normalize(org.get("title") or "")
    if not title or is_generic(title):
        # generic → ключ = title + первая категория, чтобы школа №306 и
        # школа №522 остались разными, а Дикси×N слились
        cats = org.get("categories") or []
        first_cat = normalize(cats[0].get("name", "")) if cats else ""
        return f"generic::{title}::{first_cat}"
    return f"named::{title}"


def main() -> int:
    if not IN_PATH.exists():
        print(f"[-] {IN_PATH} not found. Run 01_scrape_yandex.py first.")
        return 1

    with IN_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    orgs = data.get("organizations", [])
    print(f"[*] Input: {len(orgs)} organizations")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in orgs:
        groups[group_key(o)].append(o)

    representatives: list[dict[str, Any]] = []
    for key, group in groups.items():
        # ближайший к центру = представитель
        rep = min(group, key=lambda x: x.get("_distance_m", 1e9))
        rep["_group_key"] = key
        rep["_group_size"] = len(group)
        if len(group) > 1:
            rep["_group_members"] = [
                {"oid": g["oid"], "title": g.get("title"),
                 "address": g.get("address"), "distance_m": g.get("_distance_m")}
                for g in group
            ]
        representatives.append(rep)

    representatives.sort(key=lambda o: o.get("_distance_m", 0))

    summary = {
        **{k: v for k, v in data.items() if k != "organizations"},
        "total_after_dedup": len(representatives),
        "total_before_dedup": len(orgs),
        "organizations": representatives,
    }
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[+] Unique after dedup: {len(representatives)} (was {len(orgs)})")
    print(f"[+] Saved: {OUT_PATH}")

    # топ-20 крупных групп
    big = sorted(
        ((r["_group_size"], r.get("title", "?")) for r in representatives if r["_group_size"] > 1),
        reverse=True,
    )
    if big:
        print()
        print("Top duplicate groups:")
        for size, title in big[:20]:
            print(f"  ×{size:3d}  {title[:60]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
