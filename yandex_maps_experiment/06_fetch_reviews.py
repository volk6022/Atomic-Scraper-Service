"""Approach 6 — replay /maps/api/business/fetchReviews from inside Playwright.

The reviews endpoint is documented in §3 of the research:
  https://yandex.ru/maps/api/business/fetchReviews
  ?businessId=<oid>&from=<n>&count=<m>&ranking=by_time|by_rating

It requires a CSRF token and an established Yandex Maps session. We launch a
headless browser, navigate to the org page, then call `page.request.get(...)`
which inherits the live session cookies — the cleanest way to authenticate
against the same-origin endpoint without ever leaving the proxy session.

We pull two pages (~100 reviews) for the first SPB dentistry we discovered.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (
    playwright_proxy, ExperimentResult, log_line, utf8_stdout,
    RESULTS_DIR,
)

NAME = "06_fetch_reviews"

# Pick a known org with many reviews — Дэнтал Конфидэнс from the §4 sample
TARGET_OID = "82071161567"
TARGET_SEONAME = "dental_konfidens"
PAGE_SIZE = 50
PAGES = 2


def run() -> ExperimentResult:
    from playwright.sync_api import sync_playwright

    res = ExperimentResult(approach="fetchReviews replay (browser session)")
    t0 = time.perf_counter()
    proxy = playwright_proxy()
    org_url = f"https://yandex.ru/maps/org/{TARGET_SEONAME}/{TARGET_OID}/reviews/"

    all_reviews: list[dict] = []
    captured_meta = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, proxy=proxy,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="ru-RU", timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()

        # Collect any fetchReviews-style XHRs that the page itself makes,
        # so we can record the exact request shape Yandex actually accepts.
        observed = []

        def on_resp(resp):
            u = resp.url
            if "fetchReviews" in u or "/api/business/" in u or "/reviews/" in u and "ajax" in u:
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                observed.append({
                    "url": u,
                    "method": resp.request.method,
                    "status": resp.status,
                    "headers": dict(resp.request.headers),
                    "body_preview": body[:600],
                    "body_len": len(body),
                })
                log_line(NAME, f"[obs] {resp.request.method} {resp.status} {u[:140]}")

        page.on("response", on_resp)

        try:
            log_line(NAME, f"goto {org_url}")
            page.goto(org_url, wait_until="domcontentloaded", timeout=60_000)
            # Trigger lazy review loading
            try:
                page.wait_for_selector(".business-reviews-card-view, .business-review-view",
                                       timeout=15_000)
            except Exception:
                pass
            for _ in range(5):
                page.evaluate(
                    """() => {
                        const c = document.querySelector('.scroll__container, .business-reviews-card-view, div[class*=reviews]');
                        if (c) c.scrollBy(0, 4000);
                        window.scrollBy(0, 3000);
                    }"""
                )
                page.wait_for_timeout(1200)
            if any(s in page.content().lower() for s in ("smartcaptcha", "showcaptcha")):
                res.captcha_detected = True
                res.notes = "captcha on org page"
                return res

            # Wait for reviews tab to render
            try:
                page.wait_for_selector(".business-reviews-card-view, .business-review-view, .scroll__container",
                                       timeout=20_000)
            except Exception as e:
                log_line(NAME, f"reviews ui not detected: {e}")

            # 0) prime CSRF: first call returns {"csrfToken": "..."}
            csrf = None
            for attempt in range(3):
                try:
                    pr = page.request.get(
                        f"https://yandex.ru/maps/api/business/fetchReviews?businessId={TARGET_OID}&from=0&count=1",
                        headers={"Referer": org_url, "X-Requested-With": "XMLHttpRequest"},
                        timeout=30_000,
                    )
                    j = pr.json()
                    csrf = j.get("csrfToken")
                    log_line(NAME, f"csrf prime: status={pr.status}, got_token={'yes' if csrf else 'no'}")
                    if csrf:
                        break
                except Exception as e:
                    log_line(NAME, f"csrf prime attempt {attempt+1}: {e}")
                    time.sleep(1.5)

            # Probe fetchReviews via the live session
            for pg in range(PAGES):
                url = (
                    "https://yandex.ru/maps/api/business/fetchReviews"
                    f"?businessId={TARGET_OID}"
                    f"&from={pg * PAGE_SIZE}"
                    f"&count={PAGE_SIZE}"
                    "&ranking=by_time"
                    "&lang=ru&ajax=1"
                )
                if csrf:
                    url += f"&csrfToken={csrf}"
                r = None
                last_err = None
                for attempt in range(4):
                    try:
                        r = page.request.get(url, headers={
                            "Referer": org_url,
                            "Accept": "application/json, text/plain, */*",
                            "X-Requested-With": "XMLHttpRequest",
                        }, timeout=30_000)
                        break
                    except Exception as e:
                        last_err = e
                        log_line(NAME, f"  attempt {attempt+1}: {str(e)[:120]}")
                        time.sleep(2.0 * (attempt + 1))
                if r is None:
                    log_line(NAME, f"  giving up after retries: {last_err}")
                    continue
                log_line(NAME, f"fetchReviews page {pg}: {r.status} ({len(r.body())}B)")
                if r.status != 200:
                    log_line(NAME, f"  body snippet: {r.text()[:200]!r}")
                    continue
                try:
                    data = r.json()
                except Exception as e:
                    log_line(NAME, f"  JSON parse failed: {e}")
                    continue

                # Save raw on first page for diagnostics
                if pg == 0:
                    (RESULTS_DIR / f"{NAME}_raw_page0.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    if isinstance(data, dict):
                        captured_meta = {k: data.get(k) for k in
                                         ("csrfToken", "param", "data") if k in data}

                # Locate review array
                reviews = None
                if isinstance(data, dict):
                    for path in (("data", "reviews"), ("reviews",),
                                 ("data", "items"), ("items",)):
                        cur = data
                        ok = True
                        for k in path:
                            if isinstance(cur, dict) and k in cur:
                                cur = cur[k]
                            else:
                                ok = False
                                break
                        if ok and isinstance(cur, list):
                            reviews = cur
                            log_line(NAME, f"  reviews array at {'.'.join(path)} (len={len(cur)})")
                            break
                if reviews:
                    all_reviews.extend(reviews)
                else:
                    log_line(NAME, f"  no review array found; top-level keys = {list(data.keys())[:10] if isinstance(data, dict) else type(data)}")

                time.sleep(0.8)

        except Exception as e:
            res.error = repr(e)
            log_line(NAME, f"error: {e}")
        finally:
            (RESULTS_DIR / f"{NAME}_observed_xhrs.json").write_text(
                json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8")
            log_line(NAME, f"observed {len(observed)} review-ish XHRs")

            # If page-side XHR returned the data, use that directly
            for obs in observed:
                if obs.get("status") == 200 and obs.get("body_len", 0) > 1000:
                    try:
                        data = json.loads(obs.get("body_preview", "") if obs.get("body_len", 0) <= 600 else "")
                    except Exception:
                        data = None
                    # body_preview is truncated, so re-fetch via the live session for full content
                    if "fetchReviews" in obs["url"]:
                        try:
                            rr = page.request.get(obs["url"], headers={"Referer": org_url,
                                                                       "X-Requested-With": "XMLHttpRequest"},
                                                  timeout=30_000)
                            jj = rr.json()
                            for path in (("data", "reviews"), ("reviews",), ("data", "items"), ("items",)):
                                cur = jj
                                ok = True
                                for k in path:
                                    if isinstance(cur, dict) and k in cur:
                                        cur = cur[k]
                                    else:
                                        ok = False
                                        break
                                if ok and isinstance(cur, list):
                                    all_reviews.extend(cur)
                                    log_line(NAME, f"  pulled {len(cur)} reviews from observed-URL replay")
                                    break
                        except Exception as e:
                            log_line(NAME, f"  replay of observed URL failed: {e}")
                        break
            ctx.close()
            browser.close()

    # de-dup by review id
    seen, deduped = set(), []
    for r in all_reviews:
        if not isinstance(r, dict):
            continue
        rid = r.get("reviewId") or r.get("id") or r.get("publicId")
        if rid in seen:
            continue
        if rid:
            seen.add(rid)
        deduped.append(r)
    res.items_collected = len(deduped)
    res.success = res.items_collected > 0
    if deduped:
        res.fields_per_item = sorted({k for r in deduped for k in r.keys()})[:30]
        res.sample = deduped[:3]
        (RESULTS_DIR / f"{NAME}_reviews.json").write_text(
            json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    res.notes = f"target oid={TARGET_OID}; pages={PAGES}; per_page={PAGE_SIZE}"
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
