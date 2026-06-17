"""Эксперимент 5 (ЖИВОЙ): есть ли отзывы в SSR-HTML страницы /reviews/?

Гипотеза: как и поиск, страница отзывов рендерит первую пачку отзывов прямо в
inline-<script>. Если да — парсим напрямую (httpx, дёшево, стабильно), без
нестабильного observe-and-replay XHR fetchReviews.

Зонд: httpx GET страницы /reviews/, ищем крупные inline-JSON, рекурсивно находим
массив объектов с полями отзыва (reviewId/text/rating/author) и печатаем путь.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"

# тестовые орг: (seoname, oid, прим.кол-во отзывов)
TARGETS = [
    ("laboratoriya_31", "1544310630", 13791),
    ("mendeleev", "62690060917", 12278),
    ("pkhalikhinkali", "94066354321", 9078),
]

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


def first_proxy() -> str:
    for line in (REPO / "proxies.txt").read_text().splitlines():
        line = line.strip()
        if line.startswith("http://"):
            return line
    raise RuntimeError("no http proxy")


def looks_like_review(d) -> bool:
    if not isinstance(d, dict):
        return False
    keys = set(d.keys())
    return ("reviewId" in keys) or (
        {"text", "rating"} <= keys and ("author" in keys or "updatedTime" in keys))


def find_review_arrays(obj, path="$", out=None, depth=0):
    """Рекурсивно ищем списки, где ≥1 элемент похож на отзыв. Возвращаем [(path, len, sample_keys)]."""
    if out is None:
        out = []
    if depth > 12:
        return out
    if isinstance(obj, list):
        if obj and sum(1 for x in obj[:5] if looks_like_review(x)) >= 1:
            sample = obj[0] if isinstance(obj[0], dict) else {}
            out.append((path, len(obj), sorted(sample.keys())[:20]))
        for i, x in enumerate(obj[:50]):
            find_review_arrays(x, f"{path}[{i}]", out, depth + 1)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_review_arrays(v, f"{path}.{k}", out, depth + 1)
    return out


def big_json_blobs(html: str, min_len=20_000):
    blobs = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        t = m.group(1).strip()
        if len(t) < min_len:
            continue
        # некоторые скрипты обёрнуты в присваивание; пробуем найти JSON c фигурной скобки
        for cand in (t, t[t.find("{"):] if "{" in t else t):
            try:
                blobs.append((len(t), json.loads(cand)))
                break
            except Exception:
                continue
    return blobs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proxy = first_proxy()
    report = []
    for seoname, oid, rc in TARGETS:
        url = f"https://yandex.ru/maps/org/{seoname}/{oid}/reviews/"
        rec = {"seoname": seoname, "oid": oid, "reviews_total": rc, "url": url}
        t0 = time.time()
        try:
            with httpx.Client(proxy=proxy, headers=HEADERS, timeout=60,
                              follow_redirects=True) as c:
                r = c.get(url)
            low = r.text.lower()
            rec["status"] = r.status_code
            rec["wire_kb"] = round(r.num_bytes_downloaded / 1024, 1)
            rec["captcha"] = ("smartcaptcha" in low or "showcaptcha" in low
                              or "checkcaptcha" in low)
            blobs = big_json_blobs(r.text)
            rec["n_big_json"] = len(blobs)
            found = []
            for blen, blob in blobs:
                for path, n, keys in find_review_arrays(blob):
                    found.append({"path": path, "count": n, "keys": keys})
            # дедуп по пути
            seen = set(); uniq = []
            for f in found:
                if f["path"] not in seen:
                    seen.add(f["path"]); uniq.append(f)
            rec["review_arrays"] = uniq
            rec["max_reviews_in_ssr"] = max([f["count"] for f in uniq], default=0)
        except Exception as e:
            rec["error"] = str(e)[:160]
        rec["elapsed_s"] = round(time.time() - t0, 1)
        report.append(rec)
        print(json.dumps({k: v for k, v in rec.items() if k != "review_arrays"},
                         ensure_ascii=False))
        for f in rec.get("review_arrays", []):
            print(f"    SSR array: {f['path']}  count={f['count']}  keys={f['keys']}")
        print()
        time.sleep(2)

    (OUT / "05_reviews_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] {OUT / '05_reviews_probe.json'}")


if __name__ == "__main__":
    main()
