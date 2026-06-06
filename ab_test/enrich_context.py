"""E1+E2: фетч «контекста обогащения» из Яндекс.Карт для prefill агента.

Для каждой орг (oid+seoname) тянет httpx (через прокси, без браузера):
  - карточку /maps/org/{seoname}/{oid}/ → socialLinks, description, телефоны, часы
  - отзывы /reviews/?page=N&ranking=by_time → сниппеты за последние 6 мес (cap)

Сохраняет ab_test/context/{oid}.json. Идемпотентно.
Запуск: PYTHONIOENCODING=utf-8 uv run python ab_test/enrich_context.py
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CTX = HERE / "context"
CUTOFF = datetime.now(timezone.utc) - timedelta(days=183)
MAX_REVIEW_SNIPPETS = 12
MAX_REVIEW_PAGES = 6

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "ru-RU,ru;q=0.9",
     "Accept-Encoding": "gzip, deflate, br"}


def proxies():
    return [l.strip() for l in (REPO / "proxies.txt").read_text().splitlines()
            if l.strip().startswith("http://")]


def get(url, tries=5):
    for _ in range(tries):
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


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_card(seoname, oid):
    r = get(f"https://yandex.ru/maps/org/{seoname}/{oid}/")
    if not r:
        return {}
    item = {}
    try:
        item = big_blob(r.text)["stack"][0]["results"]["items"][0]
    except Exception:
        return {}
    social = []
    for s in item.get("socialLinks") or []:
        if isinstance(s, dict) and s.get("href"):
            social.append({"type": s.get("type"), "href": s.get("href"),
                           "label": s.get("readableHref")})
    phones = []
    for p in item.get("phones") or []:
        if isinstance(p, dict) and p.get("number"):
            phones.append(p.get("number"))
    wt = item.get("workingTime") or {}
    hours = wt.get("text") if isinstance(wt, dict) else None
    rd = item.get("ratingData") or {}
    return {
        "social_links": social,
        "description": item.get("description") or "",
        "phones": phones,
        "hours": hours,
        "rating": rd.get("ratingValue"),
        "reviews_count": rd.get("reviewCount"),
        "site": item.get("seoname") and (item.get("links") or None),
    }


def fetch_reviews(seoname, oid):
    base = f"https://yandex.ru/maps/org/{seoname}/{oid}/reviews/"
    snippets = []
    for page in range(1, MAX_REVIEW_PAGES + 1):
        r = get(base + f"?page={page}&ranking=by_time")
        if not r:
            break
        try:
            revs = big_blob(r.text)["stack"][0]["results"]["items"][0]["reviewResults"]["reviews"]
        except Exception:
            break
        if not revs:
            break
        page_in_window = 0
        for rv in revs:
            d = parse_dt(rv.get("updatedTime"))
            txt = (rv.get("text") or "").strip()
            if d and d >= CUTOFF and txt:
                page_in_window += 1
                rating = rv.get("rating")
                snippets.append({"rating": rating, "text": txt[:300],
                                 "date": d.date().isoformat()})
            if len(snippets) >= MAX_REVIEW_SNIPPETS:
                break
        if len(snippets) >= MAX_REVIEW_SNIPPETS or page_in_window == 0:
            break
        time.sleep(0.5)
    return snippets


def main():
    CTX.mkdir(parents=True, exist_ok=True)
    sel = json.load((HERE / "ab_orgs.json").open(encoding="utf-8"))
    orgs = sel["orgs"]
    for i, o in enumerate(orgs, 1):
        oid, seo = str(o["oid"]), o.get("seoname")
        out = CTX / f"{oid}.json"
        if out.exists():
            print(f"[{i}/{len(orgs)}] {oid} cached"); continue
        t0 = time.time()
        card = fetch_card(seo, oid)
        reviews = fetch_reviews(seo, oid)
        ctx = {"oid": oid, "seoname": seo, "title": o.get("title"),
               "card": card, "reviews": reviews}
        out.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{i}/{len(orgs)}] {oid} {o.get('title','?')[:24]:24} "
              f"social={len(card.get('social_links') or [])} reviews={len(reviews)} "
              f"descr={'y' if card.get('description') else 'n'} ({time.time()-t0:.1f}s)", flush=True)

    # сводка
    socs = revs_ = descr = 0
    for f in CTX.glob("*.json"):
        c = json.loads(f.read_text(encoding="utf-8"))
        socs += len(c["card"].get("social_links") or [])
        revs_ += len(c.get("reviews") or [])
        descr += 1 if c["card"].get("description") else 0
    print(f"\n[итог] контекстов={len(list(CTX.glob('*.json')))} "
          f"соц-ссылок всего={socs} отзывов всего={revs_} с описанием={descr}")


if __name__ == "__main__":
    main()
