"""Эксперимент 10 (ЖИВОЙ): отзывы «последние 6 месяцев, максимум 300» через httpx.

ranking=by_time → хронологический порядок (свежие первыми). Листаем ?page=1..,
останавливаемся когда: набрали 300, ИЛИ страница целиком старше 6 месяцев.
Проверяем формат updatedTime и что порядок действительно по времени.
"""

from __future__ import annotations

import json
import re
import time
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"

SEONAME, OID = "schastye", "1153763644"
MAX_REVIEWS = 300
MONTHS = 6
CUTOFF = datetime.now(timezone.utc) - timedelta(days=MONTHS * 30.4)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "ru-RU,ru;q=0.9",
     "Accept-Encoding": "gzip, deflate, br"}


def proxies():
    return [l.strip() for l in (REPO / "proxies.txt").read_text().splitlines()
            if l.strip().startswith("http://")]


def get(url):
    for _ in range(6):
        try:
            with httpx.Client(proxy=random.choice(proxies()), headers=H, timeout=30,
                              follow_redirects=True) as c:
                return c.get(url)
        except Exception:
            time.sleep(1)
    return None


def big_blob(html):
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        t = m.group(1).strip()
        if len(t) < 20_000:
            continue
        try:
            return json.loads(t)
        except Exception:
            try:
                return json.loads(t[t.find("{"):])
            except Exception:
                continue
    return None


def reviews_of(blob):
    try:
        return blob["stack"][0]["results"]["items"][0]["reviewResults"]["reviews"]
    except Exception:
        return []


def parse_dt(v):
    """updatedTime может быть ISO-строкой или epoch (сек/мс)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        ts = v / 1000 if v > 1e11 else v
        return datetime.fromtimestamp(ts, timezone.utc)
    s = str(v)
    if s.isdigit():
        ts = int(s); ts = ts / 1000 if ts > 1e11 else ts
        return datetime.fromtimestamp(ts, timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = f"https://yandex.ru/maps/org/{SEONAME}/{OID}/reviews/"
    collected = []
    wire = 0
    stop_reason = "max_pages"
    for page in range(1, 13):
        r = get(base + f"?page={page}&ranking=by_time")
        if not r:
            stop_reason = "fetch_fail"
            break
        wire += r.num_bytes_downloaded
        revs = reviews_of(big_blob(r.text) or {})
        if not revs:
            stop_reason = "empty_page"
            break
        dts = [parse_dt(rv.get("updatedTime")) for rv in revs]
        valid = [d for d in dts if d]
        newest = max(valid) if valid else None
        oldest = min(valid) if valid else None
        in_window = [rv for rv, d in zip(revs, dts) if d and d >= CUTOFF]
        collected.extend(in_window)
        print(f"page={page} n={len(revs)} "
              f"newest={newest.date() if newest else '?'} oldest={oldest.date() if oldest else '?'} "
              f"в_окне_6мес={len(in_window)} итого={len(collected)} {r.num_bytes_downloaded//1024}KB")
        # пример формата на первой странице
        if page == 1:
            print("  sample updatedTime:", [rv.get("updatedTime") for rv in revs[:3]])
        if len(collected) >= MAX_REVIEWS:
            stop_reason = "max_reviews"
            break
        if oldest and oldest < CUTOFF and len(in_window) < len(revs):
            stop_reason = "older_than_6mo"
            break
        time.sleep(0.7)

    collected = collected[:MAX_REVIEWS]
    print(f"\n[итог] собрано в окне 6мес: {len(collected)}  стоп={stop_reason}  "
          f"трафик={wire/1024:.0f}KB ({wire/1024/max(1,len(collected)):.1f}KB/отзыв)")
    json.dump({"collected": len(collected), "stop_reason": stop_reason,
               "wire_kb": round(wire / 1024, 1), "cutoff": CUTOFF.isoformat()},
              (OUT / "10_reviews_recent.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
