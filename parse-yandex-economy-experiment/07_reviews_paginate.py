"""Эксперимент 7 (ЖИВОЙ): полная пагинация отзывов через httpx (без браузера).

Схема:
  1. GET страницы /reviews/  → SSR: 50 отзывов + csrfToken + sessionId + totalPages,
     куки сессии оседают в httpx.Client.
  2. GET /maps/api/business/fetchReviews?page=2..N с теми же куками и csrfToken.

Проверяем: работает ли без подозрительных параметров s/reqId, растёт ли набор
уникальных reviewId, сколько байт/страница, ловится ли капча.
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

SEONAME, OID = "schastye", "1153763644"
MAX_PAGES = 4
RANKING = "by_time"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9", "Accept-Encoding": "gzip, deflate, br",
}


def http_proxies():
    return [l.strip() for l in (REPO / "proxies.txt").read_text().splitlines()
            if l.strip().startswith("http://")]


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


def find_token(obj, name, depth=0):
    if depth > 14:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == name and isinstance(v, (str, int)):
                return v
            r = find_token(v, name, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for x in obj[:30]:
            r = find_token(x, name, depth + 1)
            if r is not None:
                return r
    return None


def parse_reviews_from_ajax(data):
    """fetchReviews ajax-ответ: ищем массив reviews."""
    def rec(o, d=0):
        if d > 12:
            return None
        if isinstance(o, dict):
            if isinstance(o.get("reviews"), list):
                return o["reviews"]
            for v in o.values():
                r = rec(v, d + 1)
                if r:
                    return r
        elif isinstance(o, list):
            for x in o[:30]:
                r = rec(x, d + 1)
                if r:
                    return r
        return None
    return rec(data) or []


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proxy = random.choice(http_proxies())
    url = f"https://yandex.ru/maps/org/{SEONAME}/{OID}/reviews/"
    pages = []
    all_ids = set()
    total_wire = 0

    with httpx.Client(proxy=proxy, headers=HEADERS, timeout=50,
                      follow_redirects=True) as c:
        # ── страница 1 (SSR) ──
        r = c.get(url)
        total_wire += r.num_bytes_downloaded
        blob = big_blob(r.text)
        rr = blob["stack"][0]["results"]["items"][0]["reviewResults"]
        ssr_reviews = rr.get("reviews") or []
        csrf = find_token(blob, "csrfToken")
        session = find_token(blob, "sessionId")
        params = rr.get("params") or {}
        total_pages = params.get("totalPages")
        for rev in ssr_reviews:
            all_ids.add(rev.get("reviewId"))
        pages.append({"page": 1, "src": "ssr", "status": r.status_code,
                      "n": len(ssr_reviews), "wire_kb": round(r.num_bytes_downloaded/1024, 1)})
        print(f"page1 SSR: {len(ssr_reviews)} reviews, totalPages={total_pages}, "
              f"csrf={'yes' if csrf else 'NO'} session={'yes' if session else 'NO'}")
        print(f"  cookies: {list(c.cookies.keys())}")

        # ── страницы 2..N через fetchReviews ──
        api = "https://yandex.ru/maps/api/business/fetchReviews"
        for page in range(2, MAX_PAGES + 1):
            variants = [
                # минимальный набор
                {"ajax": "1", "businessId": OID, "csrfToken": csrf, "locale": "ru_RU",
                 "page": page, "pageSize": 50, "ranking": RANKING, "sessionId": session},
            ]
            got = None
            for params_q in variants:
                params_q = {k: v for k, v in params_q.items() if v is not None}
                try:
                    rr2 = c.get(api, params=params_q,
                                headers={"Accept": "*/*",
                                         "X-Requested-With": "XMLHttpRequest",
                                         "Referer": url})
                except Exception as e:
                    print(f"  page{page} EXC: {str(e)[:100]}")
                    continue
                total_wire += rr2.num_bytes_downloaded
                low = rr2.text.lower()
                cap = "smartcaptcha" in low or "showcaptcha" in low
                try:
                    data = rr2.json()
                    revs = parse_reviews_from_ajax(data)
                except Exception:
                    revs = []
                got = {"page": page, "src": "ajax", "status": rr2.status_code,
                       "n": len(revs), "captcha": cap,
                       "wire_kb": round(rr2.num_bytes_downloaded/1024, 1),
                       "ctype": rr2.headers.get("content-type", "")[:40]}
                new = sum(1 for rv in revs if rv.get("reviewId") not in all_ids)
                got["new_unique"] = new
                for rv in revs:
                    all_ids.add(rv.get("reviewId"))
                break
            pages.append(got)
            print(f"  page{page}: status={got['status']} n={got['n']} new={got.get('new_unique')} "
                  f"captcha={got['captcha']} {got['wire_kb']}KB ctype={got['ctype']}")
            time.sleep(1.5)

    print(f"\n[итог] уникальных reviewId={len(all_ids)} за {len(pages)} страниц, "
          f"трафик={total_wire/1024:.0f}KB")
    json.dump({"pages": pages, "unique_ids": len(all_ids),
               "total_wire_kb": round(total_wire/1024, 1)},
              (OUT / "07_reviews_paginate.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
