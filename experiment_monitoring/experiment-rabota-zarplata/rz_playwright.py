"""
rz_playwright.py — Playwright-based live verification for rabota.ru and zarplata.ru.

Verifies anonymously (no login) for EACH site:
  1. Page loads (anti-bot reality)
  2. Data source: __NEXT_DATA__ / window.__INITIAL_STATE__ / XHR JSON endpoints
  3. Extracts listing: id, title, company, salary, url, date
  4. Extracts one vacancy card
  5. Captures XHR/fetch calls to identify JSON API endpoints

Attempt order per site:
  httpx direct → httpx proxy → Playwright+stealth direct → +proxy → headed

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment_monitoring\\experiment-rabota-zarplata\\rz_playwright.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, quote

import httpx

from playwright.sync_api import Browser, BrowserContext, Page, Request, Response, sync_playwright
from playwright_stealth import Stealth

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
SAMPLES_RABOTA = SCRIPT_DIR / "samples" / "rabota"
SAMPLES_ZARPLATA = SCRIPT_DIR / "samples" / "zarplata"
SAMPLES_RABOTA.mkdir(parents=True, exist_ok=True)
SAMPLES_ZARPLATA.mkdir(parents=True, exist_ok=True)

PROXIES_FILE = SCRIPT_DIR.parent.parent / "proxies.txt"

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

RABOTA_SEARCH = "https://www.rabota.ru/vacancy/?keywords=python&sort=Date"
ZARPLATA_SEARCH = "https://www.zarplata.ru/vacancies/search/?text=python&order_by=publication_time"

# ---------------------------------------------------------------------------
# Proxy loading
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_proxy_list() -> list[dict]:
    """Return Playwright proxy dicts from proxies.txt."""
    if not PROXIES_FILE.exists():
        print(f"[WARN] proxies.txt not found at {PROXIES_FILE}")
        return []
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
    print(f"[INFO] Loaded {len(proxies)} proxies")
    return proxies


def load_httpx_proxies() -> list[str]:
    """Return URL-encoded httpx proxy strings."""
    if not PROXIES_FILE.exists():
        return []
    proxies = []
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            enc_user = quote(m.group("user"), safe="")
            enc_pass = quote(m.group("password"), safe="")
            proxies.append(f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}")
    return proxies


# ---------------------------------------------------------------------------
# httpx verification
# ---------------------------------------------------------------------------

HTTPX_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def httpx_try(url: str, proxy: Optional[str] = None, timeout: float = 20.0) -> tuple[int, str]:
    """Returns (status_code, body_text). Raises on error."""
    kwargs: dict[str, Any] = {
        "headers": HTTPX_HEADERS,
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy:
        kwargs["proxy"] = proxy
    with httpx.Client(**kwargs) as client:
        resp = client.get(url)
        return resp.status_code, resp.text


def run_httpx_attempts(url: str, site: str, samples_dir: Path) -> Optional[tuple[int, str]]:
    """Try httpx direct, then rotate proxies. Returns (status, body) or None."""
    print(f"\n[httpx] Testing {site}: {url}")

    # Direct
    try:
        status, body = httpx_try(url)
        print(f"  [httpx direct] HTTP {status} / {len(body)} bytes")
        if status == 200:
            (samples_dir / "httpx_direct_search.html").write_text(body, encoding="utf-8")
            print(f"  → Saved httpx_direct_search.html")
            return status, body
        else:
            (samples_dir / f"httpx_direct_{status}.html").write_text(body, encoding="utf-8")
    except Exception as exc:
        print(f"  [httpx direct] FAILED: {exc}")

    # Proxy rotation
    proxies = load_httpx_proxies()
    for i, proxy_url in enumerate(proxies[:10]):
        try:
            status, body = httpx_try(url, proxy=proxy_url)
            print(f"  [httpx proxy {i+1}] HTTP {status} / {len(body)} bytes via {proxy_url.split('@')[-1]}")
            if status == 200:
                (samples_dir / "httpx_proxy_search.html").write_text(body, encoding="utf-8")
                print(f"  → Saved httpx_proxy_search.html")
                return status, body
            else:
                print(f"  [httpx proxy {i+1}] Non-200, trying next")
        except Exception as exc:
            print(f"  [httpx proxy {i+1}] FAILED: {exc}")
        time.sleep(0.5)

    print(f"  [httpx] All attempts failed for {site}")
    return None


# ---------------------------------------------------------------------------
# Playwright browser factory (stealth on context, matching hh pattern)
# ---------------------------------------------------------------------------


def make_stealth_browser(pw, headless: bool = True, proxy: Optional[dict] = None) -> tuple[Browser, BrowserContext]:
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
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------


def extract_next_data(html: str) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON from HTML."""
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try without id attribute
    m = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def extract_initial_state(html: str) -> Optional[dict]:
    """Extract window.__INITIAL_STATE__ or window.__DATA__ from HTML."""
    for pattern in [
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',
        r'window\.__DATA__\s*=\s*(\{.*?\})\s*;',
        r'window\.__REDUX_STATE__\s*=\s*(\{.*?\})\s*;',
        r'window\.__STATE__\s*=\s*(\{.*?\})\s*;',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


def find_json_blobs(html: str) -> list[dict]:
    """Find any large JSON-like objects embedded in <script> tags."""
    blobs = []
    script_contents = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for sc in script_contents:
        sc = sc.strip()
        if not sc or sc.startswith('//') or not ('{' in sc and '"' in sc):
            continue
        if len(sc) < 100:
            continue
        # Try to extract JSON objects
        for m in re.finditer(r'(\{["\w])', sc):
            start = m.start()
            # Quick heuristic: if it looks like vacancy/search data
            if any(kw in sc[start:start+500] for kw in ['vacancies', 'vacancy', 'salary', 'title', 'employer']):
                blobs.append({"pos": start, "preview": sc[start:start+200]})
                break
    return blobs


# ---------------------------------------------------------------------------
# Playwright page scraper
# ---------------------------------------------------------------------------


def scrape_page_playwright(
    pw,
    url: str,
    site: str,
    samples_dir: Path,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_for_selector: Optional[str] = None,
) -> Optional[dict]:
    """
    Load URL with Playwright+stealth. Capture:
    - HTML
    - __NEXT_DATA__ / __INITIAL_STATE__
    - XHR/fetch network calls (JSON endpoints)
    - Page title + anti-bot signals

    Returns dict with findings or None on failure.
    """
    mode = "headless" if headless else "headed"
    proxy_str = f"via {proxy['server']}" if proxy else "direct"
    print(f"\n[Playwright {mode} {proxy_str}] {site}: {url}")

    browser = None
    try:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = context.new_page()

        # Capture network requests
        xhr_json: list[dict] = []

        def on_request(req: Request):
            if req.resource_type in ("xhr", "fetch"):
                xhr_json.append({"url": req.url, "method": req.method, "type": req.resource_type})

        def on_response(resp: Response):
            if resp.request.resource_type in ("xhr", "fetch"):
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = resp.json()
                        # Save first few JSON responses
                        short_url = re.sub(r'https?://[^/]+', '', resp.url)[:50].replace('/', '_')
                        fname = f"xhr_{resp.status}_{short_url[:40]}.json"
                        (samples_dir / fname).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"  [XHR JSON] {resp.status} {resp.url[:80]} → saved {fname}")
                    except Exception:
                        pass

        page.on("request", on_request)
        page.on("response", on_response)

        # Navigate
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
        except Exception as exc:
            print(f"  [goto error] {exc}")
            return None

        # Wait for key content
        try:
            if wait_for_selector:
                page.wait_for_selector(wait_for_selector, timeout=15000)
            else:
                page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass  # Proceed with whatever loaded

        time.sleep(2)  # Extra JS settle time

        # Capture page state
        title = page.title()
        html = page.content()
        final_url = page.url

        print(f"  Title: {title[:80]}")
        print(f"  Final URL: {final_url[:80]}")
        print(f"  HTML length: {len(html)}")

        # Save HTML
        (samples_dir / "playwright_search.html").write_text(html, encoding="utf-8")
        print(f"  → Saved playwright_search.html")

        # Take screenshot
        screenshot_path = samples_dir / "playwright_search.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"  → Saved playwright_search.png")

        # Detect anti-bot signals
        anti_bot_signals = []
        html_lower = html.lower()
        for sig in ["captcha", "cloudflare", "ddos-guard", "incapsula", "akamai",
                    "blocked", "access denied", "robot", "bot detection", "challenge"]:
            if sig in html_lower:
                anti_bot_signals.append(sig)

        if anti_bot_signals:
            print(f"  [ANTI-BOT SIGNALS] {anti_bot_signals}")

        # Extract embedded data
        next_data = extract_next_data(html)
        initial_state = extract_initial_state(html)
        json_blobs = find_json_blobs(html)

        findings: dict[str, Any] = {
            "url": final_url,
            "title": title,
            "html_length": len(html),
            "anti_bot_signals": anti_bot_signals,
            "xhr_json_endpoints": [x["url"] for x in xhr_json if "json" in x.get("url", "").lower() or True][:20],
            "has_next_data": next_data is not None,
            "has_initial_state": initial_state is not None,
            "json_blobs_found": len(json_blobs),
        }

        if next_data:
            (samples_dir / "next_data.json").write_text(json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  → __NEXT_DATA__ found! Saved next_data.json ({len(str(next_data))} chars)")
            findings["next_data_keys"] = list(next_data.keys()) if isinstance(next_data, dict) else []

        if initial_state:
            (samples_dir / "initial_state.json").write_text(json.dumps(initial_state, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  → __INITIAL_STATE__ found! Saved initial_state.json")

        # Try to extract a listing
        listing = extract_listing(page, site)
        if listing:
            (samples_dir / "listing_sample.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  → Extracted {len(listing)} listing items, saved listing_sample.json")
            findings["listing_sample_count"] = len(listing)
            findings["listing_first"] = listing[0] if listing else None

        # Save all XHR URLs
        (samples_dir / "xhr_urls.txt").write_text("\n".join(x["url"] for x in xhr_json), encoding="utf-8")
        print(f"  → Saved {len(xhr_json)} XHR/fetch URLs to xhr_urls.txt")

        return findings

    except Exception as exc:
        print(f"  [PLAYWRIGHT ERROR] {exc}")
        return None
    finally:
        if browser:
            browser.close()


def extract_listing(page: Page, site: str) -> list[dict]:
    """Try to extract vacancy listing from page using site-specific selectors."""
    items = []

    if site == "rabota":
        # Try rabota.ru selectors
        selectors_to_try = [
            # Modern Next.js selectors
            {"container": "[data-testid='vacancy-list-item']", "title": "h2 a, h3 a, a[data-testid='vacancy-title']"},
            {"container": ".vacancy-list__item, .vacancy-item", "title": "a.vacancy-item__title"},
            # Generic
            {"container": "article", "title": "h2 a, h3 a"},
        ]
        for sel_config in selectors_to_try:
            try:
                containers = page.query_selector_all(sel_config["container"])
                if containers:
                    print(f"  [listing] Found {len(containers)} items with '{sel_config['container']}'")
                    for c in containers[:5]:
                        title_el = c.query_selector(sel_config["title"])
                        title = title_el.inner_text() if title_el else c.inner_text()[:100]
                        href = title_el.get_attribute("href") if title_el else ""
                        items.append({"title": title.strip(), "url": href or ""})
                    if items:
                        break
            except Exception:
                pass

        # Fallback: look for vacancy links
        if not items:
            try:
                links = page.query_selector_all("a[href*='/vacancy/']")
                seen = set()
                for link in links[:10]:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text().strip()
                    if href and text and href not in seen and len(text) > 5:
                        items.append({"title": text[:100], "url": href})
                        seen.add(href)
            except Exception:
                pass

    elif site == "zarplata":
        # Try zarplata.ru selectors
        selectors_to_try = [
            {"container": "[data-testid='vacancy-card'], [data-testid='vacancy-list-item']", "title": "h2 a, a[data-testid*='title']"},
            {"container": ".vacancy-card, .vacancy-item, [class*='vacancy']", "title": "a[class*='title'], h2 a, h3 a"},
            {"container": "article, li[class*='vacancy']", "title": "a"},
        ]
        for sel_config in selectors_to_try:
            try:
                containers = page.query_selector_all(sel_config["container"])
                if containers:
                    print(f"  [listing] Found {len(containers)} items with '{sel_config['container']}'")
                    for c in containers[:5]:
                        title_el = c.query_selector(sel_config["title"])
                        title = title_el.inner_text() if title_el else c.inner_text()[:100]
                        href = title_el.get_attribute("href") if title_el else ""
                        items.append({"title": title.strip(), "url": href or ""})
                    if items:
                        break
            except Exception:
                pass

        # Fallback: look for vacancy links
        if not items:
            try:
                links = page.query_selector_all("a[href*='/vacanc']")
                seen = set()
                for link in links[:10]:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text().strip()
                    if href and text and href not in seen and len(text) > 5:
                        items.append({"title": text[:100], "url": href})
                        seen.add(href)
            except Exception:
                pass

    return items


# ---------------------------------------------------------------------------
# Vacancy card scraper
# ---------------------------------------------------------------------------


def scrape_vacancy_card(pw, vacancy_url: str, site: str, samples_dir: Path, headless: bool = True, proxy: Optional[dict] = None) -> Optional[dict]:
    """Scrape a single vacancy card page."""
    print(f"\n[Playwright card] {site}: {vacancy_url}")
    browser = None
    try:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = context.new_page()

        xhr_json: list[dict] = []

        def on_response(resp: Response):
            if resp.request.resource_type in ("xhr", "fetch"):
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = resp.json()
                        short_url = re.sub(r'https?://[^/]+', '', resp.url)[:40].replace('/', '_')
                        fname = f"card_xhr_{resp.status}_{short_url}.json"
                        (samples_dir / fname).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"  [card XHR] {resp.status} {resp.url[:80]}")
                    except Exception:
                        pass

        page.on("response", on_response)

        try:
            page.goto(vacancy_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception as exc:
            print(f"  [goto error] {exc}")

        time.sleep(1)

        html = page.content()
        title = page.title()

        # Save
        (samples_dir / "playwright_card.html").write_text(html, encoding="utf-8")
        page.screenshot(path=str(samples_dir / "playwright_card.png"))

        # Extract card fields
        card: dict[str, Any] = {"url": vacancy_url, "title": title}

        # Try generic extraction
        for selector_name, selectors in [
            ("vacancy_title", ["h1", "[data-testid='vacancy-title']", ".vacancy-title"]),
            ("company", ["[data-testid='vacancy-company']", ".vacancy-company", "a[class*='company']"]),
            ("salary", ["[data-testid='vacancy-salary']", ".vacancy-salary", "[class*='salary']"]),
        ]:
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        card[selector_name] = el.inner_text().strip()[:200]
                        break
                except Exception:
                    pass

        # Extract __NEXT_DATA__ for card
        next_data = extract_next_data(html)
        if next_data:
            (samples_dir / "card_next_data.json").write_text(json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8")
            card["has_next_data"] = True

        print(f"  Card: {card}")
        (samples_dir / "card_sample.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

        return card

    except Exception as exc:
        print(f"  [card error] {exc}")
        return None
    finally:
        if browser:
            browser.close()


# ---------------------------------------------------------------------------
# API endpoint probing (direct JSON API attempts)
# ---------------------------------------------------------------------------


def probe_api_endpoints(site: str, samples_dir: Path) -> list[dict]:
    """Try known/candidate API endpoints for each site."""
    results = []

    if site == "rabota":
        endpoints = [
            # Official API v6
            ("https://api.rabota.ru/v6/vacancies?keywords=python&sort=date_desc&limit=5", "api_v6_vacancies"),
            ("https://api.rabota.ru/v4/vacancies?q=python&page=0&count=5", "api_v4_vacancies"),
            # Internal/BFF endpoints sometimes found on Next.js sites
            ("https://www.rabota.ru/api/vacancies?keywords=python&sort=Date&page=1", "bff_vacancies"),
            ("https://www.rabota.ru/_next/data/vacancies.json?keywords=python", "next_data_vacancies"),
        ]
    else:  # zarplata
        endpoints = [
            # Official API
            ("https://api.zarplata.ru/vacancies?text=python&order_by=publication_time&per_page=5", "api_vacancies"),
            ("https://api.zarplata.ru/v2/vacancies?text=python&order_by=publication_time&per_page=5", "api_v2_vacancies"),
            # HH-style (zarplata now under HH)
            ("https://api.zarplata.ru/vacancies?text=python", "api_vacancies_simple"),
            ("https://www.zarplata.ru/api/vacancies/search?text=python&order_by=publication_time", "bff_vacancies"),
        ]

    httpx_proxies = load_httpx_proxies()
    proxy_url = httpx_proxies[0] if httpx_proxies else None

    for url, name in endpoints:
        for attempt, (use_proxy, label) in enumerate([
            (None, "direct"),
            (proxy_url, "proxy"),
        ]):
            try:
                kwargs: dict[str, Any] = {
                    "headers": {
                        "User-Agent": CHROME_UA,
                        "Accept": "application/json",
                        "Accept-Language": "ru-RU,ru;q=0.9",
                    },
                    "timeout": 15.0,
                    "follow_redirects": True,
                }
                if use_proxy:
                    kwargs["proxy"] = use_proxy
                with httpx.Client(**kwargs) as client:
                    resp = client.get(url)
                    ct = resp.headers.get("content-type", "")
                    print(f"  [API probe {label}] {resp.status_code} {url[:70]} ct={ct[:40]}")
                    results.append({
                        "url": url,
                        "status": resp.status_code,
                        "content_type": ct,
                        "via": label,
                        "body_length": len(resp.content),
                    })
                    if resp.status_code == 200 and "json" in ct:
                        (samples_dir / f"{name}_{label}.json").write_text(resp.text, encoding="utf-8")
                        print(f"    → Saved {name}_{label}.json")
                    elif resp.status_code == 200:
                        (samples_dir / f"{name}_{label}.html").write_text(resp.text[:5000], encoding="utf-8")
                    break  # Don't need proxy if direct works
            except Exception as exc:
                print(f"  [API probe {label}] FAILED {url[:60]}: {exc}")
                results.append({"url": url, "status": "error", "error": str(exc), "via": label})
        time.sleep(0.3)

    return results


# ---------------------------------------------------------------------------
# Main verification flow
# ---------------------------------------------------------------------------


def verify_site(pw, site: str, search_url: str, samples_dir: Path, proxies: list[dict]) -> dict:
    """Full verification flow for one site."""
    print(f"\n{'='*60}")
    print(f"VERIFYING: {site.upper()} — {search_url}")
    print(f"{'='*60}")

    results: dict[str, Any] = {
        "site": site,
        "search_url": search_url,
        "httpx_result": None,
        "playwright_headless_direct": None,
        "playwright_headless_proxy": None,
        "playwright_headed_direct": None,
        "api_probe_results": [],
        "data_source": "unknown",
        "verdict": "FAILED",
    }

    # Step 1: httpx direct
    httpx_result = run_httpx_attempts(search_url, site, samples_dir)
    if httpx_result:
        status, body = httpx_result
        results["httpx_result"] = {"status": status, "body_length": len(body)}
        # Check for anti-bot in httpx response
        anti_bot = [s for s in ["captcha", "cloudflare", "ddos-guard", "blocked"] if s in body.lower()]
        results["httpx_anti_bot"] = anti_bot

    # Step 2: Probe API endpoints
    print(f"\n[API Probe] {site}")
    api_results = probe_api_endpoints(site, samples_dir)
    results["api_probe_results"] = api_results

    # Step 3: Playwright headless direct
    findings = scrape_page_playwright(pw, search_url, site, samples_dir, headless=True, proxy=None)
    results["playwright_headless_direct"] = findings

    if findings and not findings.get("anti_bot_signals"):
        results["verdict"] = "SUCCESS"
        results["data_source"] = "playwright_headless_direct"

    # Step 4: Try with proxy if headless direct was blocked or failed
    if not findings or findings.get("anti_bot_signals"):
        if proxies:
            proxy = proxies[0]
            print(f"\n[Playwright headless+proxy] Using {proxy['server']}")
            findings_proxy = scrape_page_playwright(pw, search_url, site, samples_dir, headless=True, proxy=proxy)
            results["playwright_headless_proxy"] = findings_proxy
            if findings_proxy and not findings_proxy.get("anti_bot_signals"):
                results["verdict"] = "SUCCESS_PROXY"
                results["data_source"] = "playwright_headless_proxy"
                findings = findings_proxy

    # Step 5: If blocked, try headed
    if results["verdict"] == "FAILED" or (findings and findings.get("anti_bot_signals")):
        print(f"\n[Playwright HEADED direct] {site}")
        findings_headed = scrape_page_playwright(pw, search_url, site, samples_dir, headless=False, proxy=None)
        results["playwright_headed_direct"] = findings_headed
        if findings_headed and not findings_headed.get("anti_bot_signals"):
            results["verdict"] = "SUCCESS_HEADED"
            results["data_source"] = "playwright_headed_direct"
            findings = findings_headed

    # Step 6: Scrape a vacancy card if we have a listing
    if findings and findings.get("listing_first"):
        card_url = findings["listing_first"].get("url", "")
        if card_url and not card_url.startswith("http"):
            # Make absolute
            from urllib.parse import urlparse
            parsed = urlparse(search_url)
            card_url = f"{parsed.scheme}://{parsed.netloc}{card_url}"
        if card_url.startswith("http"):
            proxy = proxies[0] if proxies and results.get("data_source", "").endswith("proxy") else None
            card = scrape_vacancy_card(pw, card_url, site, samples_dir, headless=True, proxy=proxy)
            results["vacancy_card_sample"] = card

    # Determine data source type
    if findings:
        if findings.get("has_next_data"):
            results["data_source_type"] = "__NEXT_DATA__ (Next.js SSR)"
        elif findings.get("has_initial_state"):
            results["data_source_type"] = "window.__INITIAL_STATE__"
        elif findings.get("xhr_json_endpoints"):
            results["data_source_type"] = "XHR/JSON API"
        else:
            results["data_source_type"] = "HTML only (SSR)"

    return results


def main():
    print("=" * 70)
    print("RZ Playwright Verifier — rabota.ru & zarplata.ru")
    print(f"Working dir: {SCRIPT_DIR}")
    print("=" * 70)

    proxies = load_proxy_list()

    all_results: dict[str, Any] = {}

    with sync_playwright() as pw:
        # Verify rabota.ru
        rabota_results = verify_site(pw, "rabota", RABOTA_SEARCH, SAMPLES_RABOTA, proxies)
        all_results["rabota"] = rabota_results

        # Verify zarplata.ru
        zarplata_results = verify_site(pw, "zarplata", ZARPLATA_SEARCH, SAMPLES_ZARPLATA, proxies)
        all_results["zarplata"] = zarplata_results

    # Save combined results
    report_path = SCRIPT_DIR / "verification_results.json"
    report_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n\n{'='*70}")
    print(f"VERIFICATION COMPLETE")
    print(f"Results saved to: {report_path}")
    print(f"{'='*70}")

    for site, res in all_results.items():
        print(f"\n{site.upper()}:")
        print(f"  Verdict: {res.get('verdict', 'N/A')}")
        print(f"  Data source: {res.get('data_source_type', 'unknown')}")
        ab = res.get('playwright_headless_direct', {}) or {}
        print(f"  Anti-bot signals: {ab.get('anti_bot_signals', [])}")
        if res.get('vacancy_card_sample'):
            print(f"  Card: {res['vacancy_card_sample']}")

    return all_results


if __name__ == "__main__":
    main()
