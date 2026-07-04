# -*- coding: utf-8 -*-
"""
monitor.py — TEST monitor for fl.ru (RSS) + kwork.ru (anonymous JSON endpoint).

Reuses the verified anonymous paths (see wiki/auto-monitor/auto-research-{fl,kwork}.md):
  - fl.ru:  GET https://www.fl.ru/rss/all.xml [+?category=5 / =31]  (plain httpx, no proxy)
  - kwork:  POST https://kwork.ru/projects  (X-Requested-With, form-urlencoded; data.pagination.data[])

What it does each tick:
  1. Pulls new items from both sources.
  2. Dedups against seen-ids state (monitor-test/seen.json) so restarts don't re-alert.
  3. Flags items whose title/description match the ML/CV/Python keyword set.
  4. Appends every matched hit to monitor-test/hits.jsonl and logs a one-liner.

This is a TEST harness: no scoring, no notifications — just proves the polling path
works end-to-end. Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python monitor-test/monitor.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
SEEN_PATH = HERE / "seen.json"
HITS_PATH = HERE / "hits.jsonl"

POLL_INTERVAL_S = 120

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Profile keywords matched as whole tokens (word-boundary regex) over title +
# description, so e.g. "ml" does NOT match "html" and "бот" does NOT match "работа".
# Substrings ending in a stem (машинн, нейросет, детекц, ...) keep a trailing \w*
# so they catch inflected Russian forms.
KEYWORDS = [
    "python", "ml", "machine learning", "deep learning", "computer vision",
    "neural", "cv", "detection", "opencv", "ocr", "pytorch", "tensorflow",
    "yolo", "llm", "gpt", "parser", "scraping", "telegram", "data science",
    "dataset", "bot",
    # Russian stems (match inflected endings via \w*)
    "машинн", "глубок", "компьютерн", "нейросет", "детекц", "сегментац",
    "распознавани", "парсинг", "парсер", "скрейп", "телеграм",
    "анализ данных", "датасет", "автоматизац", "нейронн",
]
_KW_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(k) for k in KEYWORDS) + r")\w*",
    re.IGNORECASE | re.UNICODE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def matches(text: str) -> list[str]:
    found = {m.group(0).lower() for m in _KW_RE.finditer(text or "")}
    return sorted(found)


def load_seen() -> dict[str, set[str]]:
    if SEEN_PATH.exists():
        try:
            raw = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            return {k: set(v) for k, v in raw.items()}
        except Exception:
            pass
    return {"fl": set(), "kwork": set()}


def save_seen(seen: dict[str, set[str]]) -> None:
    # Cap stored ids so the file does not grow unbounded.
    capped = {k: list(v)[-5000:] for k, v in seen.items()}
    SEEN_PATH.write_text(json.dumps(capped, ensure_ascii=False), encoding="utf-8")


def record_hit(hit: dict) -> None:
    with HITS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(hit, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# fl.ru — RSS
# --------------------------------------------------------------------------- #
FL_FEEDS = [
    ("fl_all", "https://www.fl.ru/rss/all.xml"),
    ("fl_programming", "https://www.fl.ru/rss/all.xml?category=5"),
    ("fl_ai", "https://www.fl.ru/rss/all.xml?category=31"),
]


def poll_fl(client: httpx.Client) -> list[dict]:
    items: dict[str, dict] = {}
    for _name, url in FL_FEEDS:
        try:
            r = client.get(url, headers={"Accept": "application/rss+xml, application/xml, */*"})
            if r.status_code != 200 or not r.content.lstrip().startswith((b"<?xml", b"<rss")):
                print(f"  [fl] {url} -> HTTP {r.status_code}, not RSS", flush=True)
                continue
            root = ET.fromstring(r.content)
            ch = root.find("channel")
            if ch is None:
                continue
            for it in ch.findall("item"):
                link = (it.findtext("link") or "").strip()
                guid = (it.findtext("guid") or link).strip()
                if not guid:
                    continue
                items[guid] = {
                    "source": "fl",
                    "id": guid,
                    "title": (it.findtext("title") or "").strip(),
                    "url": link,
                    "pub_date": (it.findtext("pubDate") or "").strip(),
                    "description": (it.findtext("description") or "").strip()[:500],
                }
        except Exception as e:
            print(f"  [fl] {url} -> ERROR {e}", flush=True)
    return list(items.values())


# --------------------------------------------------------------------------- #
# kwork.ru — anonymous JSON endpoint
# --------------------------------------------------------------------------- #
KWORK_URL = "https://kwork.ru/projects"
KWORK_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://kwork.ru/projects",
    "Origin": "https://kwork.ru",
}
# c=41 Скрипты/боты/Python-ML (primary), c=11 Программирование (broader parent).
KWORK_CATEGORIES = ["41", "11"]


def _kwork_list(data: dict) -> list[dict]:
    d = data.get("data", {})
    if isinstance(d.get("pagination"), dict) and isinstance(d["pagination"].get("data"), list):
        return d["pagination"]["data"]
    if isinstance(d.get("wants"), list):
        return d["wants"]
    return []


def poll_kwork(client: httpx.Client) -> list[dict]:
    items: dict[str, dict] = {}
    for cat in KWORK_CATEGORIES:
        try:
            r = client.post(KWORK_URL, data={"c": cat}, headers=KWORK_HEADERS)
            if r.status_code != 200:
                print(f"  [kwork] c={cat} -> HTTP {r.status_code}", flush=True)
                continue
            for p in _kwork_list(r.json()):
                pid = str(p.get("id") or p.get("want_id") or "")
                if not pid:
                    continue
                items[pid] = {
                    "source": "kwork",
                    "id": pid,
                    "title": (p.get("name") or "").strip(),
                    "url": f"https://kwork.ru/projects/{pid}",
                    "price_limit": p.get("priceLimit"),
                    "possible_price_limit": p.get("possiblePriceLimit"),
                    "category_id": p.get("category_id"),
                    "offers": p.get("kwork_count"),
                    "description": (p.get("description") or "").strip()[:500],
                }
        except Exception as e:
            print(f"  [kwork] c={cat} -> ERROR {e}", flush=True)
    return list(items.values())


# --------------------------------------------------------------------------- #
# main loop
# --------------------------------------------------------------------------- #
def tick(client: httpx.Client, seen: dict[str, set[str]]) -> None:
    for src, poller in (("fl", poll_fl), ("kwork", poll_kwork)):
        fetched = poller(client)
        new = [it for it in fetched if it["id"] not in seen[src]]
        matched = 0
        for it in new:
            seen[src].add(it["id"])
            hit_kw = matches(f"{it.get('title','')} {it.get('description','')}")
            if hit_kw:
                matched += 1
                rec = {"ts": now_iso(), "keywords": hit_kw, **it}
                record_hit(rec)
                price = it.get("price_limit") or ""
                print(f"  >> HIT [{src}] {it.get('title','')[:70]} {price}  {it.get('url','')}", flush=True)
        print(f"  [{src}] fetched={len(fetched)} new={len(new)} matched={matched}", flush=True)
    save_seen(seen)


def main() -> None:
    seen = load_seen()
    print(f"=== monitor start {now_iso()} | interval={POLL_INTERVAL_S}s | "
          f"seen(fl)={len(seen['fl'])} seen(kwork)={len(seen['kwork'])} ===", flush=True)
    with httpx.Client(follow_redirects=True, timeout=30.0,
                      headers={"User-Agent": CHROME_UA}) as client:
        while True:
            print(f"--- tick {now_iso()} ---", flush=True)
            try:
                tick(client, seen)
            except Exception as e:
                print(f"  TICK ERROR: {e}", flush=True)
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
