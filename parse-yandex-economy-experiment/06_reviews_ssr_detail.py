"""Эксперимент 6 (ЖИВОЙ): метаданные SSR отзывов + механизм пагинации.

Цель: понять, можно ли листать отзывы через httpx напрямую (нужен csrf/cursor),
или придётся оставлять браузерный replay. Дамп структуры reviewResults + поиск
csrf-токена и параметров пагинации. Ретрай по нескольким прокси.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"

TARGETS = [
    ("pkhalikhinkali", "94066354321"),
    ("mendeleev", "62690060917"),
    ("the_byk", "141991862997"),
    ("schastye", "1153763644"),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9", "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
}


def http_proxies():
    return [l.strip() for l in (REPO / "proxies.txt").read_text().splitlines()
            if l.strip().startswith("http://")]


def get_with_retry(url, proxies, tries=4):
    last = None
    for i in range(tries):
        try:
            with httpx.Client(proxy=proxies[i % len(proxies)], headers=HEADERS,
                              timeout=40, follow_redirects=True) as c:
                r = c.get(url)
            return r
        except Exception as e:
            last = e
            time.sleep(1)
    raise last


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


def keyshape(d, maxk=40):
    if isinstance(d, dict):
        return {k: keyshape(v, maxk) if k not in ("reviews",) else f"<list[{len(v)}]>"
                for k, v in list(d.items())[:maxk]} if False else sorted(d.keys())
    return type(d).__name__


def search_tokens(obj, out=None, depth=0):
    """Ищем поля, похожие на csrf/token/sessionId/requestId/pager/cursor."""
    if out is None:
        out = {}
    if depth > 14:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if any(s in kl for s in ("csrf", "token", "sessionid", "requestid",
                                     "cursor", "nextpage", "pager", "offset", "page")):
                if isinstance(v, (str, int, float, bool)) or v is None:
                    out.setdefault(k, str(v)[:80])
                elif isinstance(v, dict):
                    out.setdefault(k, {kk: str(vv)[:60] for kk, vv in list(v.items())[:8]})
            search_tokens(v, out, depth + 1)
    elif isinstance(obj, list):
        for x in obj[:30]:
            search_tokens(x, out, depth + 1)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proxies = http_proxies()
    report = []
    for seoname, oid in TARGETS:
        url = f"https://yandex.ru/maps/org/{seoname}/{oid}/reviews/"
        rec = {"seoname": seoname, "oid": oid}
        try:
            r = get_with_retry(url, proxies)
            rec["status"] = r.status_code
            rec["wire_kb"] = round(r.num_bytes_downloaded / 1024, 1)
            low = r.text.lower()
            rec["captcha"] = "captcha" in low and ("smartcaptcha" in low or "showcaptcha" in low)
            rec["set_cookies"] = [c.split("=")[0] for c in r.headers.get_list("set-cookie")][:12]
            blob = big_blob(r.text)
            if blob:
                try:
                    rr = blob["stack"][0]["results"]["items"][0]["reviewResults"]
                    rec["reviewResults_keys"] = sorted(rr.keys())
                    rec["ssr_reviews"] = len(rr.get("reviews") or [])
                    # всё, что не reviews — это метаданные пагинации
                    rec["meta"] = {k: (v if isinstance(v, (str, int, float, bool, type(None)))
                                       else (sorted(v.keys()) if isinstance(v, dict)
                                             else f"<{type(v).__name__}>"))
                                   for k, v in rr.items() if k != "reviews"}
                except Exception as e:
                    rec["parse_meta_err"] = str(e)[:100]
                rec["tokens"] = search_tokens(blob)
        except Exception as e:
            rec["error"] = str(e)[:160]
        report.append(rec)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        print()
        time.sleep(2)

    (OUT / "06_reviews_detail.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
