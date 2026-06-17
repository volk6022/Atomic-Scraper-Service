"""Approach 4 — Playwright + playwright-stealth + XHR intercept.

Same as approach 3, but:
  * apply playwright-stealth to mask navigator.webdriver and other tells
  * capture all responses from yandex.ru/maps/api/* and search-maps.yandex.ru/v1/
  * extract richer fields straight from the captured JSON (coordinates, phones,
    rubric IDs, photos, etc.) — these are not in the DOM.

This is the "hybrid: browser bootstrap + replay XHR" pattern from §10.2 of the
research doc.
"""
from __future__ import annotations

import json
import re
import time

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (
    playwright_proxy, ExperimentResult, log_line, utf8_stdout,
    TARGET_QUERY, SPB_REGION_ID, RESULTS_DIR,
)

NAME = "04_playwright_xhr_intercept"
TARGET_ITEMS = 40
SCROLL_LIMIT = 25


def run() -> ExperimentResult:
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import Stealth
        stealth_available = True
    except ImportError:
        stealth_available = False
        log_line(NAME, "playwright-stealth not installed, falling back to plain")

    res = ExperimentResult(approach="Playwright + stealth + XHR intercept")
    t0 = time.perf_counter()

    proxy = playwright_proxy()
    url = f"https://yandex.ru/maps/{SPB_REGION_ID}/saint-petersburg/search/{TARGET_QUERY}/"

    captured = []  # list[(url, status, body_text)]

    def on_response(response):
        u = response.url
        if "/maps/api/search" in u or "search-maps.yandex.ru" in u or "/maps/api/business" in u or "fullobjects" in u:
            try:
                txt = response.text()
            except Exception:
                txt = ""
            captured.append({"url": u, "status": response.status, "len": len(txt), "body": txt})
            log_line(NAME, f"XHR {response.status} {u[:120]} ({len(txt)}B)")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--disable-blink-features=AutomationControlled"],
        )
        if stealth_available:
            ctx = browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
        else:
            ctx = browser.new_context(locale="ru-RU", timezone_id="Europe/Moscow")
        page = ctx.new_page()
        if stealth_available:
            try:
                Stealth().apply_stealth_sync(page)
            except Exception as e:
                log_line(NAME, f"stealth apply failed: {e}")

        page.on("response", on_response)
        try:
            log_line(NAME, f"goto {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            html_low = page.content().lower()
            if "smartcaptcha" in html_low or "showcaptcha" in html_low:
                res.captcha_detected = True
                res.notes = "captcha on first load"
                return res
            try:
                page.wait_for_selector(".search-list-view, .search-snippet-view", timeout=20_000)
            except Exception as e:
                res.notes = f"results panel never appeared: {e}"
                return res

            # Scroll
            seen_count, stale = 0, 0
            for i in range(SCROLL_LIMIT):
                count = page.evaluate(
                    "() => document.querySelectorAll('li.search-snippet-view, div.search-snippet-view').length"
                )
                if count >= TARGET_ITEMS:
                    break
                if count == seen_count:
                    stale += 1
                    if stale >= 3:
                        break
                else:
                    stale = 0
                seen_count = count
                page.evaluate(
                    """() => {
                       const list = document.querySelector('.scroll__container, .search-list-view__list, .search-list-view')
                                  || document.querySelector('div[class*=search-list]');
                       if (list) list.scrollBy(0, 2000);
                       window.scrollBy(0, 1500);
                    }"""
                )
                page.wait_for_timeout(900)
            log_line(NAME, f"final card count: {seen_count}")

        except Exception as e:
            res.error = repr(e)
        finally:
            ctx.close()
            browser.close()

    # Save raw captures (with bodies, gzip-friendly text)
    raw_path = RESULTS_DIR / f"{NAME}_captures.json"
    raw_path.write_text(
        json.dumps(captured, ensure_ascii=False)[:25_000_000],  # cap for safety
        encoding="utf-8",
    )
    log_line(NAME, f"saved {len(captured)} raw captures -> {raw_path} ({raw_path.stat().st_size}B)")

    # Parse captured JSON for org items — prefer top-level `data.items` shape
    org_items = []
    for cap in captured:
        body = cap.get("body", "")
        if not body or len(body) < 80:
            continue
        try:
            data = json.loads(body)
        except Exception:
            continue

        # Yandex /maps/api/search returns roughly:
        #   {"data": {"items": [{"name":..., "seoname":..., "permalink":..., ...}], "geo": {...}}, "csrfToken": ...}
        items_arr = None
        if isinstance(data, dict):
            for path in (("data", "items"), ("items",), ("data", "geo", "items")):
                cur = data
                ok = True
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, list):
                    items_arr = cur
                    log_line(NAME, f"top-level items array at {'.'.join(path)} len={len(cur)}")
                    break

        if items_arr:
            for it in items_arr:
                if isinstance(it, dict) and (("permalink" in it) or ("seoname" in it) or ("oid" in it)):
                    org_items.append(it)

    # de-dup by permalink/oid/seoname
    seen, deduped = set(), []
    for it in org_items:
        key = it.get("permalink") or it.get("oid") or it.get("seoname") or it.get("id")
        if key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(it)
    log_line(NAME, f"XHR captures: {len(captured)}, org-like objects: {len(org_items)}, dedup: {len(deduped)}")

    res.items_collected = len(deduped)
    res.success = res.items_collected > 0
    if deduped:
        res.fields_per_item = sorted({k for d in deduped for k in d.keys()})[:40]
        res.sample = deduped[:3]
        (RESULTS_DIR / f"{NAME}_items.json").write_text(
            json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    res.notes = f"captured {len(captured)} XHR responses; {len(deduped)} org objects after dedup"
    res.duration_s = round(time.perf_counter() - t0, 2)
    return res


def main() -> int:
    utf8_stdout()
    res = run()
    res.save(NAME)
    log_line(NAME, f"verdict: success={res.success} items={res.items_collected} "
                   f"captcha={res.captcha_detected} duration_s={res.duration_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
