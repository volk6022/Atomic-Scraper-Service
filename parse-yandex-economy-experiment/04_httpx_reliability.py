"""Эксперимент 4 (ЖИВОЙ): устойчивость httpx-подхода (капча? блоки?) на выборке.

Гоняем ~16 запросов по разным точкам ll и категориям, ротируя прокси так же,
как прод (round-robin по proxies.txt). Считаем: долю капчи, не-200, среднее орг,
суммарный трафик «по проводу». Это де-риск перед рекомендацией отказаться от браузера.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from urllib.parse import quote

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"
CLAT, CLON = 59.914403, 30.327319
ZOOM = 17

CATS = ["кафе", "стоматология", "аптека", "салон красоты", "магазин",
        "ресторан", "автосервис", "цветы"]
# смещения центра ячейки (в метрах) — имитируем разные точки сетки
OFFSETS_M = [(0, 0), (300, 300), (-600, 400), (800, -800)]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none",
}


def http_proxies():
    out = []
    for line in (REPO / "proxies.txt").read_text().splitlines():
        line = line.strip()
        if line.startswith("http://"):
            out.append(line)
    return out


def extract_ssr(html: str):
    import re
    best = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        t = m.group(1)
        if len(t) < 50_000:
            continue
        try:
            d = json.loads(t)
        except Exception:
            continue
        stack = d.get("stack") if isinstance(d, dict) else None
        if isinstance(stack, list) and stack and isinstance(stack[0], dict):
            res = stack[0].get("results")
            if isinstance(res, dict) and isinstance(res.get("items"), list):
                if len(res["items"]) > len(best):
                    best = res["items"]
    return best


def offset_ll(dx, dy):
    dlat = dy / 111320.0
    dlon = dx / (111320.0 * math.cos(math.radians(CLAT)))
    return CLAT + dlat, CLON + dlon


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proxies = http_proxies()
    jobs = []
    pi = 0
    for k, (dx, dy) in enumerate(OFFSETS_M):
        lat, lon = offset_ll(dx, dy)
        for cat in CATS[:4]:  # 4 точки × 4 категории = 16 запросов
            jobs.append((cat, lat, lon, proxies[pi % len(proxies)]))
            pi += 1

    results = []
    total_wire = 0
    for n, (cat, lat, lon, proxy) in enumerate(jobs, 1):
        url = (f"https://yandex.ru/maps/2/saint-petersburg/search/"
               f"{quote(cat, safe='')}/?ll={lon},{lat}&z={ZOOM}")
        rec = {"n": n, "cat": cat, "proxy": proxy.split('@')[-1]}
        t0 = time.time()
        try:
            with httpx.Client(proxy=proxy, headers=HEADERS, timeout=60,
                              follow_redirects=True) as c:
                r = c.get(url)
            low = r.text.lower()
            rec["status"] = r.status_code
            rec["wire_kb"] = round(r.num_bytes_downloaded / 1024, 1)
            total_wire += r.num_bytes_downloaded
            rec["captcha"] = ("smartcaptcha" in low or "showcaptcha" in low
                              or "checkcaptcha" in low)
            rec["orgs"] = len(extract_ssr(r.text))
        except Exception as e:
            rec["error"] = str(e)[:120]
        rec["s"] = round(time.time() - t0, 1)
        print(json.dumps(rec, ensure_ascii=False))
        results.append(rec)
        time.sleep(1.5)

    n = len(results)
    ok = sum(1 for r in results if r.get("orgs"))
    cap = sum(1 for r in results if r.get("captcha"))
    bad = sum(1 for r in results if r.get("status") not in (200, None) or r.get("error"))
    orgs = [r["orgs"] for r in results if r.get("orgs")]
    print(f"\n[итог] запросов={n}  с_данными={ok}  капча={cap}  ошибок/не-200={bad}")
    print(f"  ср.орг={sum(orgs)/max(1,len(orgs)):.1f}  "
          f"суммарный трафик={total_wire/1024/1024:.2f} МБ  "
          f"ср.на_запрос={total_wire/1024/max(1,n):.0f} КБ")
    json.dump({"results": results, "total_wire_mb": round(total_wire/1024/1024, 3),
               "captcha": cap, "ok": ok, "n": n},
              (OUT / "04_reliability.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
