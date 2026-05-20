"""Approach 3 — vanilla Playwright + RU residential proxy.

Loads the SPB search page in headless Chromium, scrolls the results panel to
trigger lazy-loading, and harvests organization cards from the rendered DOM.
The same selectors as Approach 1c are used, but here JS executes so we should
get far more than the 5 SSR-only cards.
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

NAME = "03_playwright_basic"
TARGET_ITEMS = 40
SCROLL_LIMIT = 25  # generous upper bound


def run() -> ExperimentResult:
    from playwright.sync_api import sync_playwright

    res = ExperimentResult(approach="Playwright headless + RU residential proxy")
    t0 = time.perf_counter()

    proxy = playwright_proxy()
    url = (
        f"https://yandex.ru/maps/{SPB_REGION_ID}/saint-petersburg/search/"
        f"{TARGET_QUERY}/"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        try:
            log_line(NAME, f"goto {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # Detect captcha early
            content = page.content().lower()
            if "smartcaptcha" in content or "showcaptcha" in content:
                res.captcha_detected = True
                res.notes = "captcha on first load"
                return res

            # Wait for search panel
            try:
                page.wait_for_selector(".search-list-view, .search-snippet-view", timeout=20_000)
            except Exception as e:
                res.notes = f"results panel not found: {e}"
                return res

            # Scroll the results list to trigger lazy loads
            seen_count = 0
            stale = 0
            for i in range(SCROLL_LIMIT):
                count = page.evaluate(
                    "() => document.querySelectorAll('li.search-snippet-view, div.search-snippet-view').length"
                )
                log_line(NAME, f"scroll iter {i}: cards={count}")
                if count >= TARGET_ITEMS:
                    break
                if count == seen_count:
                    stale += 1
                    if stale >= 3:
                        break
                else:
                    stale = 0
                seen_count = count
                # Scroll inside the results panel
                page.evaluate(
                    """() => {
                       const list = document.querySelector('.scroll__container, .search-list-view__list, .search-list-view')
                                  || document.querySelector('div[class*=search-list]');
                       if (list) list.scrollBy(0, 2000);
                       window.scrollBy(0, 1500);
                    }"""
                )
                page.wait_for_timeout(900)

            html = page.content()
            (RESULTS_DIR / f"{NAME}_raw.html").write_text(html, encoding="utf-8")

            # Re-parse via Playwright DOM API (faster than BS for big DOM)
            items = page.evaluate(
                """() => {
                  const cards = Array.from(document.querySelectorAll('li.search-snippet-view, div.search-snippet-view'));
                  const out = [];
                  for (const c of cards) {
                    const link = c.querySelector('a[href*="/maps/org/"]');
                    const href = link ? link.getAttribute('href') : null;
                    const m = href && href.match(/\\/maps\\/org\\/([^/]+)\\/(\\d+)\\//);
                    const q = (sel) => { const el = c.querySelector(sel); return el ? el.innerText.trim() : null; };
                    out.push({
                      name: q('.search-business-snippet-view__title, .search-snippet-view__title'),
                      categories_text: q('.search-business-snippet-view__category, .business-categories-text-view'),
                      address: q('.search-business-snippet-view__address, .search-snippet-view__address'),
                      rating: q('.business-rating-badge-view__rating-text, .business-rating-badge-view__rating'),
                      reviews_text: q('.business-rating-amount-view, .search-business-snippet-view__rating-and-amount'),
                      working_status: q('.business-working-status-view'),
                      seoname: m ? m[1] : null,
                      business_oid: m ? m[2] : null,
                      url: href,
                    });
                  }
                  return out;
                }"""
            )
            # de-dup by oid
            seen, deduped = set(), []
            for it in items:
                oid = it.get("business_oid")
                if oid and oid in seen:
                    continue
                if oid:
                    seen.add(oid)
                deduped.append(it)
            log_line(NAME, f"final cards={len(items)} dedup={len(deduped)}")
            res.items_collected = len(deduped)
            res.success = res.items_collected > 0
            if deduped:
                res.fields_per_item = sorted({k for d in deduped for k in d.keys() if d.get(k)})
                res.sample = deduped[:5]
                (RESULTS_DIR / f"{NAME}_items.json").write_text(
                    json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            res.error = repr(e)
            log_line(NAME, f"error: {e}")
        finally:
            ctx.close()
            browser.close()

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
