"""Эксперимент 3 (ЖИВОЙ): можно ли получить SSR-данные БЕЗ браузера (httpx GET)?

Если Яндекс отдаёт страницу поиска с SSR-JSON обычному HTTP-клиенту без капчи —
это убирает браузер целиком: ~0.5 МБ/запрос, высокая параллельность, нет CPU
на рендеринг. Главный риск — SmartCaptcha для не-JS клиента.

Тестируем несколько категорий через те же прокси, считаем байты и орги.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"
CLAT, CLON = 59.914403, 30.327319
ZOOM = 17
QUERIES = ["кафе", "стоматология", "аптека"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def first_proxy() -> str:
    for line in (REPO / "proxies.txt").read_text().splitlines():
        line = line.strip()
        if line.startswith("http://"):
            return line
    raise RuntimeError("no http proxy")


def extract_ssr(html: str):
    """Вытащить items из самого большого inline-JSON в HTML."""
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proxy = first_proxy()
    results = []
    for q in QUERIES:
        url = (f"https://yandex.ru/maps/2/saint-petersburg/search/"
               f"{quote(q, safe='')}/?ll={CLON},{CLAT}&z={ZOOM}")
        t0 = time.time()
        rec = {"query": q}
        try:
            with httpx.Client(proxy=proxy, headers=HEADERS, timeout=60,
                              follow_redirects=True) as c:
                r = c.get(url)
            body = r.content
            rec["status"] = r.status_code
            # num_bytes_downloaded = сырые (сжатые) байты «по проводу» = то, что биллит прокси
            rec["wire_kb"] = round(r.num_bytes_downloaded / 1024, 1)
            rec["decoded_kb"] = round(len(body) / 1024, 1)
            rec["content_encoding"] = r.headers.get("content-encoding", "—")
            text = r.text
            low = text.lower()
            rec["captcha"] = ("smartcaptcha" in low or "showcaptcha" in low
                              or "checkcaptcha" in low)
            items = extract_ssr(text)
            rec["orgs"] = len(items)
            rec["has_ssr"] = bool(items)
            if items:
                oids = [str(it.get("id") or it.get("oid") or "") for it in items]
                rec["sample_oids"] = [o for o in oids if o][:3]
        except Exception as e:
            rec["error"] = str(e)[:160]
        rec["elapsed_s"] = round(time.time() - t0, 1)
        print(json.dumps(rec, ensure_ascii=False))
        results.append(rec)
        time.sleep(2)

    (OUT / "03_httpx_ssr.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("orgs"))
    cap = sum(1 for r in results if r.get("captcha"))
    print(f"\n[итог] запросов={len(results)} с_данными={ok} капча={cap}")


if __name__ == "__main__":
    main()
