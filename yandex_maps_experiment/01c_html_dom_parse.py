"""Approach 1c — parse the server-rendered DOM of the SPB search page.

The SPA renders the first viewport of business cards on the server. We can
extract them with BeautifulSoup without ever calling the JSON API. (Subsequent
pages are loaded by client JS, so this approach only gets the first ~10-15
results — but for a "list of orgs by category" use case it's a useful baseline.)
"""
from __future__ import annotations

import json
import re
import time
import urllib3

import requests
from bs4 import BeautifulSoup

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (
    requests_proxies, ExperimentResult, log_line, utf8_stdout,
    TARGET_QUERY, SPB_REGION_ID, RESULTS_DIR,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NAME = "01c_html_dom_parse"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def fetch_html(proxies, attempts=4):
    url = f"https://yandex.ru/maps/{SPB_REGION_ID}/saint-petersburg/search/{requests.utils.quote(TARGET_QUERY)}/"
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    last = None
    for i in range(attempts):
        try:
            return requests.get(url, headers=headers, proxies=proxies, timeout=30, verify=False)
        except Exception as e:
            last = e
            log_line(NAME, f"hiccup {i+1}: {str(e)[:120]}")
            time.sleep(2 * (i + 1))
    raise last


def parse_cards(html: str):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.search-snippet-view") or soup.select("div.search-snippet-view")
    out = []
    for card in cards:
        item = {}
        # name
        name = card.select_one(".search-business-snippet-view__title, .search-snippet-view__title, .search-snippet-title-view__title")
        if name:
            item["name"] = name.get_text(strip=True)
        # categories
        cat = card.select_one(".search-business-snippet-view__category, .search-snippet-view__category, .business-categories-text-view")
        if cat:
            item["categories_text"] = cat.get_text(strip=True)
        # address
        addr = card.select_one(".search-business-snippet-view__address, .search-snippet-view__address")
        if addr:
            item["address"] = addr.get_text(strip=True)
        # rating + reviews
        rating = card.select_one(".business-rating-badge-view__rating-text, .business-rating-badge-view__rating")
        if rating:
            item["rating"] = rating.get_text(strip=True)
        revs = card.select_one(".business-rating-amount-view, .search-business-snippet-view__rating-and-amount")
        if revs:
            item["reviews_text"] = revs.get_text(strip=True)
        # url -> oid
        link = card.select_one('a[href*="/maps/org/"]')
        if link:
            href = link.get("href", "")
            item["url"] = href
            m = re.search(r"/maps/org/([^/]+)/(\d+)/", href)
            if m:
                item["seoname"] = m.group(1)
                item["business_oid"] = m.group(2)
        # working hours (current state)
        hours = card.select_one(".business-working-status-view, .business-hours-text-view")
        if hours:
            item["working_status"] = hours.get_text(strip=True)
        # all text for debugging
        item["_text_preview"] = card.get_text(" ", strip=True)[:200]
        out.append(item)
    return out


def main() -> int:
    utf8_stdout()
    proxies = requests_proxies()
    res = ExperimentResult(approach="HTML DOM parse (BeautifulSoup, no JS)")
    t0 = time.perf_counter()

    r = fetch_html(proxies)
    res.http_status = r.status_code
    log_line(NAME, f"GET -> {r.status_code} ({len(r.content)}B)")

    html = r.text
    if "showcaptcha" in html.lower() or "smartcaptcha" in html.lower():
        res.captcha_detected = True
        res.notes = "captcha returned"
    else:
        items = parse_cards(html)
        # de-dup by oid
        seen, deduped = set(), []
        for it in items:
            oid = it.get("business_oid")
            if oid and oid in seen:
                continue
            if oid:
                seen.add(oid)
            deduped.append(it)
        log_line(NAME, f"raw cards parsed: {len(items)}, after dedup by oid: {len(deduped)}")
        res.items_collected = len(deduped)
        res.success = res.items_collected > 0
        if deduped:
            res.fields_per_item = sorted({k for d in deduped for k in d.keys() if not k.startswith("_")})
            res.sample = deduped[:5]
            # save full list
            (RESULTS_DIR / f"{NAME}_items.json").write_text(
                json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
        res.notes = (
            f"Only server-rendered viewport ({len(deduped)} cards). Remaining "
            f"results in the SPA require scrolling, i.e. JS execution."
        )

    res.duration_s = round(time.perf_counter() - t0, 2)
    res.save(NAME)
    log_line(NAME, f"verdict: success={res.success} items={res.items_collected} "
                   f"captcha={res.captcha_detected} fields={res.fields_per_item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
