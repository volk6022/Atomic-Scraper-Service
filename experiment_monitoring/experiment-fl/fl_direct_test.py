# -*- coding: utf-8 -*-
"""
fl_direct_test.py - Quick test: Playwright+stealth DIRECT (no proxy) on fl.ru
Uses the proven hh.ru Stealth class pattern applied to the context.

Run from repo root:
  cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
  uv run python experiment-fl/fl_direct_test.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(exist_ok=True)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def run_direct_playwright():
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    results = {}

    stealth = Stealth(
        navigator_user_agent_override=CHROME_UA,
        navigator_languages_override=("ru-RU", "ru"),
        navigator_platform_override="Win32",
        navigator_vendor_override="Google Inc.",
        webgl_vendor_override="Intel Inc.",
        webgl_renderer_override="Intel Iris OpenGL Engine",
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=CHROME_UA,
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
            },
        )
        stealth.apply_stealth_sync(context)

        # Capture XHR/Fetch
        xhr_requests = []
        xhr_responses = []

        def on_request(req):
            if req.resource_type in ("xhr", "fetch"):
                xhr_requests.append({
                    "url": req.url,
                    "method": req.method,
                    "post_data": req.post_data,
                })

        def on_response(resp):
            if resp.request.resource_type in ("xhr", "fetch"):
                try:
                    body = resp.body()
                    body_str = body.decode("utf-8", errors="replace")
                    if body_str.lstrip().startswith(("{", "[")):
                        xhr_responses.append({
                            "url": resp.url,
                            "status": resp.status,
                            "body_trimmed": body_str[:1500],
                        })
                except Exception:
                    pass

        page = context.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        print("Navigating to https://www.fl.ru/projects/ (DIRECT, no proxy)...")
        resp = page.goto("https://www.fl.ru/projects/", wait_until="domcontentloaded", timeout=40000)
        time.sleep(6)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        status = resp.status if resp else None
        title = page.title()
        html = page.content()
        print(f"  Status: {status}, Title: {title}")

        # Anti-bot check
        if "b-post" in html or "disposable-project-id" in html:
            verdict = "REAL-CONTENT"
        elif "ddos-guard" in html.lower():
            verdict = "DDOS-GUARD-CHALLENGE"
        elif "checking" in html.lower() or "just a moment" in html.lower():
            verdict = "JS-CHALLENGE"
        else:
            verdict = f"UNKNOWN (status={status})"
        print(f"  Anti-bot verdict: {verdict}")

        pids = re.findall(r'/projects/(\d{5,8})/', html)
        pids = list(dict.fromkeys(pids))
        print(f"  Project IDs found: {len(pids)} -- sample: {pids[:5]}")

        # Check budget visibility
        amounts = re.findall(r'<span[^>]*text-4[^>]*>(.*?)</span>', html, re.DOTALL)
        amounts_clean = [re.sub(r'\s+', ' ', a).strip()[:80] for a in amounts if a.strip()]
        print(f"  Budget amounts (text-4): {amounts_clean[:5]}")

        # Screenshot
        ss_path = SAMPLES / "fl_pw_direct_screenshot.png"
        try:
            page.screenshot(path=str(ss_path))
            print(f"  Screenshot saved: {ss_path}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        # XHR summary
        print(f"\n  XHR requests captured: {len(xhr_requests)}")
        seen_urls = set()
        for r in xhr_requests:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                print(f"    {r['method']:6s} {r['url'][:120]}")

        print(f"\n  JSON XHR responses: {len(xhr_responses)}")
        for r in xhr_responses:
            print(f"    [{r['status']}] {r['url'][:80]}")
            print(f"           {r['body_trimmed'][:200]}")

        results = {
            "mode": "direct_no_proxy",
            "status": status,
            "title": title,
            "anti_bot_verdict": verdict,
            "project_ids_count": len(pids),
            "project_ids_sample": pids[:10],
            "budget_amounts_sample": amounts_clean[:10],
            "xhr_requests_count": len(xhr_requests),
            "xhr_unique_urls": list(seen_urls),
            "xhr_json_responses": xhr_responses,
        }

        # Also test Python category
        print("\nNavigating to /projects/category/programmirovanie/python/...")
        resp2 = page.goto(
            "https://www.fl.ru/projects/category/programmirovanie/python/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(4)
        html2 = page.content()
        pids2 = list(dict.fromkeys(re.findall(r'/projects/(\d{5,8})/', html2)))
        amounts2 = re.findall(r'<span[^>]*text-4[^>]*>(.*?)</span>', html2, re.DOTALL)
        amounts2_clean = [re.sub(r'\s+', ' ', a).strip()[:80] for a in amounts2 if a.strip()]
        print(f"  Status: {resp2.status if resp2 else None}")
        print(f"  Project IDs: {len(pids2)} -- sample: {pids2[:5]}")
        print(f"  Budget amounts: {amounts2_clean[:5]}")
        results["python_category"] = {
            "status": resp2.status if resp2 else None,
            "project_ids_count": len(pids2),
            "project_ids_sample": pids2[:10],
            "budget_amounts_sample": amounts2_clean[:10],
        }

        page.close()
        browser.close()

    # Save results
    out_path = SAMPLES / "fl_direct_test.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out_path}")
    print(f"\n=== VERDICT: {results['anti_bot_verdict']} ===")
    return results


if __name__ == "__main__":
    run_direct_playwright()
