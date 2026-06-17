"""Эксперимент 11 (ЖИВОЙ): КОНКРЕТНОЕ содержимое богатых полей карточки орг.

Показываем реальные значения полей, которых нет/беднее в выдаче поиска:
описание, neurosummary (AI-саммари отзывов), features/атрибуты, меню/товары,
фото, ссылки/соцсети, related places, встроенные отзывы.
"""

from __future__ import annotations

import json
import re
import time
import random
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"

TARGETS = [("schastye", "1153763644"), ("bbeauty", None)]  # ресторан + салон

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


def short(v, n=300):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s[:n] + ("…" if len(s) > n else "")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # дополним oid для bbeauty из organizations.json
    data = json.load((REPO / "yandex_enrichment_experiment" / "data" /
                      "organizations.json").open(encoding="utf-8"))
    by_seo = {o["seoname"]: o for o in data["organizations"] if o.get("seoname")}

    out = []
    for seo, oid in TARGETS:
        if not oid:
            oid = by_seo.get(seo, {}).get("oid")
        if not oid:
            continue
        r = get(f"https://yandex.ru/maps/org/{seo}/{oid}/")
        if not r:
            print(seo, "FAIL")
            continue
        blob = big_blob(r.text) or {}
        try:
            item = blob["stack"][0]["results"]["items"][0]
        except Exception:
            print(seo, "no item")
            continue

        print(f"\n{'='*70}\n{item.get('title')}  ({seo}/{oid})  [{r.num_bytes_downloaded//1024}KB]\n{'='*70}")
        # описание
        print("• description:", short(item.get("description")))
        # neurosummary (AI-саммари)
        ns = item.get("neurosummaryData")
        print("• neurosummaryData keys:", list(ns.keys()) if isinstance(ns, dict) else ns)
        if isinstance(ns, dict):
            print("   ", short(ns, 400))
        # features / атрибуты
        feats = item.get("features") or item.get("featuresFull") or []
        print(f"• features: {len(feats)}")
        for f in feats[:6]:
            if isinstance(f, dict):
                print("    -", f.get("name"), "=", short(f.get("value"), 80))
        # меню / товары / прайс
        for k in ("goods", "menu", "prices", "priceList", "tycoon", "showcase"):
            if item.get(k):
                print(f"• {k}:", short(item.get(k), 200))
        # фото
        ph = item.get("photos")
        if isinstance(ph, dict):
            print(f"• photos: count={ph.get('count')} items={len(ph.get('items') or [])}")
        # ссылки/соцсети
        print("• links:", short(item.get("links"), 200))
        print("• socialLinks:", short(item.get("socialLinks"), 200))
        # related places
        rp = item.get("relatedPlaces")
        if rp:
            names = [p.get("title") or p.get("name") for p in (rp if isinstance(rp, list) else rp.get("items", []))][:8]
            print("• relatedPlaces:", names)
        # встроенные отзывы
        try:
            rr = item["reviewResults"]
            print(f"• reviewResults: {len(rr.get('reviews', []))} отзывов, всего={rr.get('params',{}).get('count')}")
        except Exception:
            pass
        # рейтинг/аспекты
        print("• ratingData:", short(item.get("ratingData"), 200))

        out.append({"seo": seo, "oid": oid, "keys": sorted(item.keys()),
                    "has_description": bool(item.get("description")),
                    "has_neurosummary": bool(item.get("neurosummaryData")),
                    "n_features": len(feats)})
        time.sleep(2)

    json.dump(out, (OUT / "11_card_content.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[+] {OUT / '11_card_content.json'}")


if __name__ == "__main__":
    main()
