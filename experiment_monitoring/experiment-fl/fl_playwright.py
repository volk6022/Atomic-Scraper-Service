"""
fl_playwright.py -- Playwright+stealth parser for fl.ru.

VERIFIED 2026-06-18: DDoS-Guard is bypassed by headless Playwright + stealth
(Stealth class applied to the context) DIRECT — NO PROXY NEEDED.

Plain httpx also works (returns HTTP 200 with full SSR HTML) for RSS and
listing pages. Playwright is only needed if you want XHR capture or JS filter
manipulation.

Architecture confirmed 2026-06-18:
  - Projects listing is PURE SSR-HTML. No hidden project-list XHR endpoint.
  - XHR endpoints on page load: /countries/, /prof_groups/, /projects/session/filter/
    None of these return the project list; they are UI metadata/state endpoints.
  - Budget IS visible anonymously (span.text-4 inside div.b-post__price).
  - 20-30 project IDs per page load (anonymous session).
  - No pagination links in HTML; pagination mechanism not determined.

Confirmed selectors (verified 2026-06-18):
  Project card:   a[data-disposable-project-id="<ID>"]  -> title text + href
  Budget:         div.b-post__price > span.text-4
  Body:           div.b-post__body
  Category:       <category> in RSS feed (e.g. "Программирование / Python")
  Project URL:    https://www.fl.ru/projects/<ID>/<slug>.html
                  (bare /projects/<ID>/ redirects to slug form)

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-fl\\fl_playwright.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from playwright_stealth import Stealth

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

PROXIES_FILE = Path(__file__).parent.parent / "proxies.txt"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

# Confirmed working CSS selectors (verified 2026-06-18)
SELECTORS = {
    # Listing page
    "project_card": "a[data-disposable-project-id]",   # anchor containing title + project ID attr
    "budget": "div.b-post__price span.text-4",          # budget amount (anonymous visible)
    "body_text": "div.b-post__body",                    # project description preview

    # Project card page
    "project_title": "h1",
    "category_breadcrumb": "div.b-post__category",      # category path
}

# ---------------------------------------------------------------------------
# Proxy loading
# ---------------------------------------------------------------------------

def load_proxy_list() -> list[dict]:
    """Return Playwright proxy dicts from proxies.txt."""
    if not PROXIES_FILE.exists():
        return []
    _LINE_RE = re.compile(
        r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
    )
    proxies = []
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            proxies.append({
                "server": f"http://{m.group('host')}:{m.group('port')}",
                "username": m.group("user"),
                "password": m.group("password"),
            })
    return proxies

# ---------------------------------------------------------------------------
# Browser factory
# ---------------------------------------------------------------------------

def make_stealth_browser(
    pw,
    headless: bool = True,
    proxy: Optional[dict] = None,
) -> tuple[Browser, BrowserContext]:
    """
    Launch Chromium with stealth + real UA. Returns (browser, context).
    IMPORTANT: Stealth is applied to the CONTEXT (not the page) — this is the
    proven pattern from hh.ru that defeats DDoS-Guard with headless=True.
    """
    stealth = Stealth(
        navigator_user_agent_override=CHROME_UA,
        navigator_languages_override=("ru-RU", "ru"),
        navigator_platform_override="Win32",
        navigator_vendor_override="Google Inc.",
        webgl_vendor_override="Intel Inc.",
        webgl_renderer_override="Intel Iris OpenGL Engine",
    )
    launch_kwargs: dict = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    }
    if proxy:
        launch_kwargs["proxy"] = proxy

    browser = pw.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        viewport=VIEWPORT,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        user_agent=CHROME_UA,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context

# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def goto_page(context: BrowserContext, url: str, wait_s: int = 6) -> Page:
    """Navigate to URL, wait for networkidle, return page."""
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=40000)
    time.sleep(wait_s)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return page

# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_project_list(page: Page) -> list[dict]:
    """
    Extract project cards from a listing page.

    Strategy 1: DOM via a[data-disposable-project-id] anchors
    Strategy 2: regex on /projects/<ID>/ in HTML

    Returns list of dicts with: id, title, budget, link
    """
    results = []
    html = page.content()

    # Strategy 1: DOM
    cards = page.query_selector_all(SELECTORS["project_card"])
    if cards:
        for anchor in cards:
            pid = anchor.get_attribute("data-disposable-project-id") or ""
            href = anchor.get_attribute("href") or ""
            title = anchor.inner_text().strip()
            if not href.startswith("http"):
                href = "https://www.fl.ru" + href

            # Budget: find closest b-post__price sibling in parent
            budget = ""
            try:
                parent = anchor.evaluate_handle("el => el.closest('.b-post')")
                if parent:
                    budget_el = page.evaluate(
                        "el => el ? el.querySelector('div.b-post__price span.text-4') : null",
                        parent,
                    )
                    if budget_el:
                        budget = page.evaluate("el => el ? el.innerText.trim() : ''", budget_el)
            except Exception:
                pass

            if pid or title:
                results.append({
                    "id": pid,
                    "title": title,
                    "budget": budget,
                    "link": href,
                    "_source": "dom",
                })

    # Strategy 2: regex fallback
    if not results:
        for m in re.finditer(r'href="(/projects/(\d{5,8})/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            href, pid, title = m.group(1), m.group(2), m.group(3)
            title_clean = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', title)).strip()
            results.append({
                "id": pid,
                "title": title_clean[:120],
                "budget": "",
                "link": "https://www.fl.ru" + href,
                "_source": "regex",
            })

    # Deduplicate by ID
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    return deduped


def scrape_listing(
    url: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 6,
) -> list[dict]:
    """
    One-shot: load a listing page and return project list.

    Confirmed working URLs (no auth required, httpx also works):
      https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/
      https://www.fl.ru/projects/category/programmirovanie/python/
      https://www.fl.ru/projects/category/programmirovanie/
    """
    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = goto_page(context, url, wait_s=wait_s)
        results = extract_project_list(page)
        page.close()
        browser.close()
    return results


# ---------------------------------------------------------------------------
# Standalone verification runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="fl.ru Playwright scraper")
    parser.add_argument(
        "--url",
        default="https://www.fl.ru/projects/category/ai-iskusstvenniy-intellekt/",
        help="URL to scrape",
    )
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    parser.add_argument("--proxy-port", default=None, help="Proxy port to use (11000-11099)")
    args = parser.parse_args()

    headless = args.headless == "true"

    proxy = None
    if args.proxy_port:
        proxy = {
            "server": f"http://np.puls-proxy.com:{args.proxy_port}",
            "username": "efea0cd216087051c2e6__cr.ru;sessttl.10",
            "password": "fc6a3125b4c606fa",
        }

    print(f"Scraping: {args.url}")
    print(f"Headless: {headless}, Proxy: {proxy is not None}")

    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)

        # Capture XHR for evidence
        xhr_requests = []
        xhr_responses = []

        def on_request(req):
            if req.resource_type in ("xhr", "fetch"):
                xhr_requests.append({"url": req.url, "method": req.method})

        def on_response(resp):
            if resp.request.resource_type in ("xhr", "fetch"):
                try:
                    body = resp.body().decode("utf-8", errors="replace")
                    if body.lstrip().startswith(("{", "[")):
                        xhr_responses.append({
                            "url": resp.url,
                            "status": resp.status,
                            "body_trimmed": body[:1500],
                        })
                except Exception:
                    pass

        page = context.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(args.url, wait_until="domcontentloaded", timeout=40000)
        time.sleep(6)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        html = page.content()
        projects = extract_project_list(page)

        # Screenshot
        ss_path = SAMPLES_DIR / "fl_pw_production.png"
        try:
            page.screenshot(path=str(ss_path))
        except Exception as e:
            print(f"Screenshot failed: {e}")

        page.close()
        browser.close()

    print(f"\nProjects extracted: {len(projects)}")
    for p in projects[:10]:
        budget_disp = p.get("budget", "")[:40] if p.get("budget") else "(none)"
        print(f"  [{p['id']}] {p['title'][:60]!r} | budget: {budget_disp}")

    print(f"\nXHR endpoints captured ({len(xhr_requests)}):")
    seen_xhr = set()
    for r in xhr_requests:
        if r["url"] not in seen_xhr:
            seen_xhr.add(r["url"])
            print(f"  {r['method']:6s} {r['url'][:110]}")

    # Save evidence
    evidence = {
        "url": args.url,
        "headless": headless,
        "proxy_used": proxy is not None,
        "projects_count": len(projects),
        "projects_sample": projects[:10],
        "xhr_requests": list(seen_xhr),
        "xhr_json_responses": xhr_responses,
        "anti_bot_verdict": "REAL-CONTENT" if projects else "EMPTY-OR-BLOCKED",
        "stealth_applied_to_context": True,
    }
    ev_path = SAMPLES_DIR / "fl_playwright_evidence.json"
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidence saved: {ev_path}")
