"""
superjob_playwright.py — Phase 2 Playwright+stealth parser for superjob.ru.

STRATEGY: superjob.ru is SSR (full HTML on first load), NO JS execution required
for core data. httpx direct works fine (Cloudflare does not block plain GET).
Playwright is used as fallback if Cloudflare challenge fires.

DATA SOURCES (both verified 2026-06-18):
  1. JSON-LD <script type="application/ld+json"> @type=ItemList  → vacancy IDs + URLs
  2. JSON-LD <script type="application/ld+json"> @type=JobPosting → vacancy card full data
  3. window.APP_STATE embedded JSON                               → structured vacancy fields
  4. f-test-search-result-item DOM blocks                        → title + salary + date

KEY VERIFIED FACTS (2026-06-18):
  - www.superjob.ru redirects to geo-subdomain (e.g. spb.superjob.ru)
  - russia.superjob.ru returns nationwide results (no geo restriction)
  - Search URL: https://russia.superjob.ru/vacancy/search/?keywords=...&sort_by=date_updated&order=desc&page=N
  - Vacancy card URL: https://[geo].superjob.ru/vakansii/[slug]-[id].html
  - Anti-bot: Cloudflare WAF present but NOT blocking plain httpx GET (as of 2026-06-18)
  - No DataDome detected
  - Official API: https://api.superjob.ru/2.0/vacancies/ — requires X-Api-App-Id header
  - catalogues filter: /vacancy/search/?keywords=...&catalogues[0]=48 (IT=48, 33=IT/Telecom)

Run from repo root:
  uv run python experiment_monitoring/experiment-superjob/superjob_playwright.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
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

PROXIES_FILE = Path(__file__).parent.parent.parent / "proxies.txt"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEARCH_URL = (
    "https://russia.superjob.ru/vacancy/search/"
    "?keywords=Python&sort_by=date_updated&order=desc&page=1"
)
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

HTTPX_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# ---------------------------------------------------------------------------
# Proxy loading (shared with experiment-hh)
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^https?://"
    r"(?P<user>[^:@]+)"
    r":"
    r"(?P<password>[^@]+)"
    r"@"
    r"(?P<host>[^:]+)"
    r":"
    r"(?P<port>\d+)$"
)


def load_proxy_list_playwright() -> list[dict]:
    """Return Playwright proxy dicts from proxies.txt."""
    if not PROXIES_FILE.exists():
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
    return proxies


def load_proxy_list_httpx() -> list[str]:
    """Return URL-encoded proxy strings for httpx."""
    import urllib.parse
    if not PROXIES_FILE.exists():
        return []
    proxies = []
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            enc_user = urllib.parse.quote(m.group("user"), safe="")
            enc_pass = urllib.parse.quote(m.group("password"), safe="")
            proxies.append(
                f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}"
            )
    return proxies


# ---------------------------------------------------------------------------
# HTML Extraction (verified selectors / patterns — 2026-06-18)
# ---------------------------------------------------------------------------

def extract_vacancies_from_html(html: str) -> list[dict]:
    """
    Extract vacancy listing from search results page HTML.

    PRIMARY: JSON-LD @type=ItemList (vacancy IDs + URLs, always present in SSR)
    SECONDARY: window.APP_STATE (structured entity data, present if page fully loaded)
    TERTIARY: f-test-search-result-item DOM blocks (title/salary/date)

    Returns list of dicts with keys:
      id, title, company, salary_min, salary_max, salary_agreement, url, published_at, slug
    """
    results_by_id: dict[str, dict] = {}

    # --- Step 1: Extract IDs and URLs from JSON-LD ItemList ---
    ld_scripts = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    for s in ld_scripts:
        try:
            data = json.loads(s)
            if data.get("@type") == "ItemList":
                for item in data.get("itemListElement", []):
                    url = item.get("url", "")
                    m = re.search(r"/vakansii/(.+?)-(\d+)\.html$", url)
                    if m:
                        vid = m.group(2)
                        results_by_id[vid] = {
                            "id": vid,
                            "slug": m.group(1),
                            "url": url,
                            "position": item.get("position", 0),
                            "title": "",
                            "company": "",
                            "salary_min": 0,
                            "salary_max": 0,
                            "salary_agreement": False,
                            "published_at": "",
                            "_source": "ld_json_itemlist",
                        }
        except Exception:
            pass

    # --- Step 2: Enrich with window.APP_STATE (vacancyMainInfo entities) ---
    idx = html.find("window.APP_STATE=")
    if idx >= 0:
        raw = html[idx + len("window.APP_STATE="):]
        depth = 0
        end = 0
        for i, c in enumerate(raw[:500000]):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if depth == 0 and i > 0:
                end = i + 1
                break
        if end > 0:
            try:
                state = json.loads(raw[:end])
                entities = state.get("entities", {})

                for vid, vac_entity in entities.get("vacancyMainInfo", {}).items():
                    attrs = vac_entity.get("attributes", {})
                    if vid not in results_by_id:
                        results_by_id[vid] = {
                            "id": vid,
                            "slug": "",
                            "url": "",
                            "position": 0,
                            "title": "",
                            "company": "",
                            "salary_min": 0,
                            "salary_max": 0,
                            "salary_agreement": False,
                            "published_at": "",
                            "_source": "app_state_main_info",
                        }
                    results_by_id[vid]["title"] = attrs.get("profession", "")
                    results_by_id[vid]["published_at"] = attrs.get("publishedAt", "")
                    results_by_id[vid]["salary_min"] = attrs.get("minSalary", 0)
                    results_by_id[vid]["salary_max"] = attrs.get("maxSalary", 0)
                    if not results_by_id[vid]["_source"].startswith("ld"):
                        results_by_id[vid]["_source"] = "app_state_main_info"

                for vid, sal_entity in entities.get("vacancySalary", {}).items():
                    attrs = sal_entity.get("attributes", {})
                    if vid in results_by_id:
                        results_by_id[vid]["salary_min"] = attrs.get("minSalary", 0)
                        results_by_id[vid]["salary_max"] = attrs.get("maxSalary", 0)
                        results_by_id[vid]["salary_agreement"] = attrs.get(
                            "paymentAgreement", False
                        )

                for vid, comp_entity in entities.get("vacancyCompanyInfo", {}).items():
                    attrs = comp_entity.get("attributes", {})
                    if vid in results_by_id:
                        results_by_id[vid]["company"] = attrs.get("name", "")

            except Exception as e:
                print(f"  [warn] APP_STATE parse error: {e}")

    # --- Step 3: Fill titles from f-test-search-result-item blocks if missing ---
    cards_raw = re.split(r"(?=<div[^>]+f-test-search-result-item)", html)
    card_titles = []
    card_dates = []
    for card in cards_raw[1:]:
        # Title: text in f-test-link anchor
        link_m = re.search(r'f-test-link-[A-Z][^"]*"[^>]*><span[^>]*>([^<]+)<', card)
        title = link_m.group(1).strip() if link_m else ""
        # Date
        date_m = re.search(
            r"((?:Сегодня|Вчера|Позавчера) в \d{2}:\d{2}|\d{1,2} \w+ \d{4})", card[:2000]
        )
        date = date_m.group(1) if date_m else ""
        card_titles.append(title)
        card_dates.append(date)

    # Match cards to results by position order
    ordered_results = sorted(results_by_id.values(), key=lambda x: x["position"])
    for i, vac in enumerate(ordered_results):
        if i < len(card_titles) and card_titles[i] and not vac["title"]:
            vac["title"] = card_titles[i]
        if i < len(card_dates) and card_dates[i] and not vac["published_at"]:
            vac["published_at"] = card_dates[i]

    return ordered_results


def extract_vacancy_card(html: str, vacancy_id: str) -> dict:
    """
    Extract full vacancy card fields from individual vacancy page HTML.

    VERIFIED DATA SOURCES:
    1. JSON-LD @type=JobPosting — title, company, salary, datePosted, location, description
    2. window.APP_STATE entities — vacancyMainInfo, vacancySalary, vacancyDetailInfo, vacancyCompanyInfo
    """
    result: dict = {
        "id": vacancy_id,
        "title": "",
        "company": "",
        "salary_min": 0,
        "salary_max": 0,
        "salary_agreement": False,
        "currency": "RUB",
        "published_at": "",
        "town": "",
        "address": "",
        "experience": "",
        "description": "",
        "duties": "",
        "requirements": "",
        "employment_type": "",
        "contacts_available": False,
    }

    # --- Source 1: JSON-LD JobPosting ---
    ld_scripts = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    for s in ld_scripts:
        try:
            data = json.loads(s)
            if data.get("@type") == "JobPosting":
                result["title"] = data.get("title", "")
                result["published_at"] = data.get("datePosted", "")
                result["employment_type"] = data.get("employmentType", "")
                org = data.get("hiringOrganization", {})
                result["company"] = org.get("name", "")
                loc = data.get("jobLocation", {})
                addr = loc.get("address", {})
                result["town"] = addr.get("addressLocality", "")
                result["address"] = addr.get("streetAddress", "")
                result["description"] = re.sub(r"<[^>]+>", " ", data.get("description", ""))[:500]
                sal = data.get("baseSalary", {})
                val = sal.get("value", {})
                result["salary_min"] = val.get("minValue", 0)
                result["salary_max"] = val.get("maxValue", 0)
                result["currency"] = sal.get("currency", "RUB")
                result["_source"] = "ld_json_jobposting"
        except Exception:
            pass

    # --- Source 2: window.APP_STATE entities ---
    idx = html.find("window.APP_STATE=")
    if idx >= 0:
        raw = html[idx + len("window.APP_STATE="):]
        depth = 0
        end = 0
        for i, c in enumerate(raw[:500000]):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if depth == 0 and i > 0:
                end = i + 1
                break
        if end > 0:
            try:
                state = json.loads(raw[:end])
                entities = state.get("entities", {})

                vac_main = entities.get("vacancyMainInfo", {}).get(vacancy_id, {})
                if vac_main:
                    attrs = vac_main.get("attributes", {})
                    if not result["title"]:
                        result["title"] = attrs.get("profession", "")
                    if not result["published_at"]:
                        result["published_at"] = attrs.get("publishedAt", "")
                    result["salary_min"] = attrs.get("minSalary", 0) or result["salary_min"]
                    result["salary_max"] = attrs.get("maxSalary", 0) or result["salary_max"]

                vac_detail = entities.get("vacancyDetailInfo", {}).get(vacancy_id, {})
                if vac_detail:
                    attrs = vac_detail.get("attributes", {})
                    result["duties"] = attrs.get("duties", "")[:300]
                    result["requirements"] = attrs.get("requirements", "")[:300]

                vac_sal = entities.get("vacancySalary", {}).get(vacancy_id, {})
                if vac_sal:
                    attrs = vac_sal.get("attributes", {})
                    result["salary_min"] = attrs.get("minSalary", 0) or result["salary_min"]
                    result["salary_max"] = attrs.get("maxSalary", 0) or result["salary_max"]
                    result["salary_agreement"] = attrs.get("paymentAgreement", False)

                vac_comp = entities.get("vacancyCompanyInfo", {}).get(vacancy_id, {})
                if vac_comp:
                    attrs = vac_comp.get("attributes", {})
                    if not result["company"]:
                        result["company"] = attrs.get("name", "")

            except Exception as e:
                print(f"  [warn] APP_STATE vacancy card parse error: {e}")

    return result


# ---------------------------------------------------------------------------
# httpx fetch helpers
# ---------------------------------------------------------------------------

def fetch_httpx(url: str, proxy: str | None = None, timeout: float = 25.0) -> tuple[int, str]:
    """Fetch URL with httpx. Returns (status_code, html). Returns (-1, msg) on error."""
    try:
        kwargs: dict = {
            "headers": HTTPX_HEADERS,
            "timeout": timeout,
            "follow_redirects": True,
        }
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as client:
            resp = client.get(url)
            return resp.status_code, resp.text
    except Exception as exc:
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Playwright browser factory (same pattern as experiment-hh)
# ---------------------------------------------------------------------------

def make_stealth_browser(
    pw,
    headless: bool = True,
    proxy: Optional[dict] = None,
) -> tuple[Browser, BrowserContext]:
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
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context


def fetch_playwright(
    url: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 5,
) -> tuple[int, str]:
    """Fetch URL with Playwright+stealth. Returns (status_code, html)."""
    try:
        with sync_playwright() as pw:
            browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=40000)
            time.sleep(wait_s)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            html = page.content()
            status = response.status if response else -1
            page.close()
            browser.close()
        return status, html
    except Exception as exc:
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Main verification runner
# ---------------------------------------------------------------------------

def run_verification(headless: bool = True) -> dict:
    """
    Run full verification flow: attempts (a)-(d).
    Returns evidence dict.
    """
    evidence: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "search_url": SEARCH_URL,
        "attempts": [],
        "best_method": None,
        "vacancies_found": 0,
        "vacancy_card_sample": None,
        "antibot_reality": None,
    }

    html: str | None = None
    used_method = None

    # --- (a) httpx direct ---
    print("\n=== (a) httpx direct ===")
    status, html_try = fetch_httpx(SEARCH_URL, proxy=None)
    print(f"  HTTP {status}, size={len(html_try)}")
    blocked_a = _is_blocked(html_try, status)
    evidence["attempts"].append({"method": "httpx_direct", "status": status, "blocked": blocked_a})
    if not blocked_a and status == 200:
        html = html_try
        used_method = "httpx_direct"
        print("  → PASS")
        (SAMPLES_DIR / "search_httpx_direct.html").write_text(html_try, encoding="utf-8")

    # --- (b) httpx via RU proxy (if (a) failed) ---
    if html is None:
        print("\n=== (b) httpx via RU proxy ===")
        proxies_httpx = load_proxy_list_httpx()
        for i, proxy in enumerate(proxies_httpx[:5]):
            print(f"  Trying proxy #{i+1}...")
            status, html_try = fetch_httpx(SEARCH_URL, proxy=proxy)
            print(f"  HTTP {status}, size={len(html_try)}")
            blocked = _is_blocked(html_try, status)
            evidence["attempts"].append({
                "method": f"httpx_proxy_{i+1}",
                "proxy_host": proxy.split("@")[-1],
                "status": status,
                "blocked": blocked,
            })
            if not blocked and status == 200:
                html = html_try
                used_method = f"httpx_proxy_{i+1}"
                print("  → PASS")
                (SAMPLES_DIR / f"search_httpx_proxy{i+1}.html").write_text(html_try, encoding="utf-8")
                break
            time.sleep(1)

    # --- (c) Playwright+stealth direct (if httpx failed) ---
    if html is None:
        print("\n=== (c) Playwright+stealth headless direct ===")
        status, html_try = fetch_playwright(SEARCH_URL, headless=True, proxy=None)
        print(f"  HTTP {status}, size={len(html_try)}")
        blocked = _is_blocked(html_try, status)
        evidence["attempts"].append({"method": "playwright_direct", "status": status, "blocked": blocked})
        if not blocked and status == 200:
            html = html_try
            used_method = "playwright_direct"
            print("  → PASS")
            (SAMPLES_DIR / "search_playwright_direct.html").write_text(html_try, encoding="utf-8")

    # --- (d) Playwright+stealth via RU proxy ---
    if html is None:
        print("\n=== (d) Playwright+stealth via RU proxy ===")
        proxies_pw = load_proxy_list_playwright()
        for i, proxy in enumerate(proxies_pw[:3]):
            print(f"  Trying proxy #{i+1}...")
            status, html_try = fetch_playwright(SEARCH_URL, headless=True, proxy=proxy)
            print(f"  HTTP {status}, size={len(html_try)}")
            blocked = _is_blocked(html_try, status)
            evidence["attempts"].append({
                "method": f"playwright_proxy_{i+1}",
                "proxy_host": proxy.get("server", "?"),
                "status": status,
                "blocked": blocked,
            })
            if not blocked and status == 200:
                html = html_try
                used_method = f"playwright_proxy_{i+1}"
                print("  → PASS")
                (SAMPLES_DIR / f"search_playwright_proxy{i+1}.html").write_text(html_try, encoding="utf-8")
                break
            time.sleep(2)

    if html is None:
        print("\n=== BLOCKED: All methods failed ===")
        evidence["best_method"] = None
        evidence["antibot_reality"] = "FULLY_BLOCKED"
        _save_evidence(evidence)
        return evidence

    # --- Extract vacancies ---
    evidence["best_method"] = used_method
    vacancies = extract_vacancies_from_html(html)
    evidence["vacancies_found"] = len(vacancies)
    evidence["vacancies_sample"] = vacancies[:10]

    print(f"\n=== Extracted {len(vacancies)} vacancies via {used_method} ===")
    for v in vacancies[:5]:
        sal = f"{v['salary_min']}" if v["salary_min"] else ("по дог." if v["salary_agreement"] else "N/A")
        print(f"  [{v['position']:2d}] {v['id']}: {v['title'][:45]!r} | {sal} | {v['published_at'][:16]!r}")
        print(f"         {v['url']}")

    # Detect anti-bot reality
    evidence["antibot_reality"] = _classify_antibot(html, used_method)

    # --- Fetch one vacancy card ---
    if vacancies:
        # Pick first vacancy with a real title
        target = next((v for v in vacancies if v.get("title")), vacancies[0])
        card_url = target.get("url") or f"https://russia.superjob.ru/vakansii/{target['slug']}-{target['id']}.html"
        print(f"\n=== Fetching vacancy card: {card_url} ===")
        time.sleep(2)

        # Use same method as search
        if "playwright" in used_method:
            proxy_pw = (
                load_proxy_list_playwright()[0]
                if "proxy" in used_method
                else None
            )
            card_status, card_html = fetch_playwright(card_url, headless=True, proxy=proxy_pw)
        else:
            proxy_httpx = None
            if "proxy" in used_method:
                px = load_proxy_list_httpx()
                proxy_httpx = px[0] if px else None
            card_status, card_html = fetch_httpx(card_url, proxy=proxy_httpx)

        print(f"  HTTP {card_status}, size={len(card_html)}")
        if card_status == 200:
            card_path = SAMPLES_DIR / f"vacancy_{target['id']}_playwright.html"
            card_path.write_text(card_html, encoding="utf-8")
            card_data = extract_vacancy_card(card_html, target["id"])
            print(f"  Card data: {json.dumps(card_data, ensure_ascii=False, indent=2)}")
            evidence["vacancy_card_sample"] = card_data

    _save_evidence(evidence)
    return evidence


def _is_blocked(html: str, status: int) -> bool:
    """Return True if the response is a block page."""
    if status in (403, 429, 503, -1):
        return True
    if len(html) < 5000:
        return True
    lower = html.lower()
    if "captcha" in lower and "vacancy" not in lower:
        return True
    if "access denied" in lower and len(html) < 20000:
        return True
    return False


def _classify_antibot(html: str, method: str) -> str:
    lower = html.lower()
    signals = []
    if "cloudflare" in lower:
        signals.append("cloudflare_js_present")
    if "turnstile" in lower:
        signals.append("turnstile_captcha")
    if "datadome" in lower:
        signals.append("datadome")
    if not signals:
        signals.append("no_antibot_signals")
    return f"PASS via {method} | signals: {', '.join(signals)}"


def _save_evidence(evidence: dict) -> None:
    path = SAMPLES_DIR / "playwright_evidence.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {path}")


# ---------------------------------------------------------------------------
# Convenience: scrape_search_page / scrape_vacancy (production use)
# ---------------------------------------------------------------------------

def scrape_search_page(
    keywords: str,
    page: int = 1,
    sort_by: str = "date_updated",
    geo: str = "russia",
    catalogues: list[int] | None = None,
    headless: bool = True,
) -> list[dict]:
    """
    Fetch vacancy search results. Returns list of vacancy dicts.

    Parameters:
        keywords:  search keywords (e.g. "Python", "machine learning")
        page:      page number (1-based)
        sort_by:   "date_updated" (newest first) | "date_posted" | "salary_desc" | "relevance"
        geo:       "russia" (nationwide) | "moscow" | "spb" (redirects to geo subdomain)
        catalogues: IT catalogue IDs (e.g. [48] for IT/Internet)

    URL pattern:
        https://russia.superjob.ru/vacancy/search/?keywords={kw}&sort_by=date_updated
            &order=desc&page={page}[&catalogues[0]=48]
    """
    import urllib.parse
    base_url = f"https://{geo}.superjob.ru/vacancy/search/"
    params: dict = {
        "keywords": keywords,
        "sort_by": sort_by,
        "order": "desc",
        "page": str(page),
    }
    if catalogues:
        for i, cat_id in enumerate(catalogues):
            params[f"catalogues[{i}]"] = str(cat_id)

    url = base_url + "?" + urllib.parse.urlencode(params, safe="[]")
    status, html = fetch_httpx(url)
    if status != 200 or _is_blocked(html, status):
        # Fallback to Playwright
        status, html = fetch_playwright(url, headless=headless)
    return extract_vacancies_from_html(html)


def scrape_vacancy(vacancy_id: str, slug: str = "", geo: str = "russia") -> dict:
    """
    Fetch a single vacancy card. Returns vacancy dict.

    URL: https://{geo}.superjob.ru/vakansii/{slug}-{vacancy_id}.html
    """
    url = f"https://{geo}.superjob.ru/vakansii/{slug}-{vacancy_id}.html" if slug else \
          f"https://russia.superjob.ru/vakansii/{vacancy_id}.html"
    status, html = fetch_httpx(url)
    if status != 200 or _is_blocked(html, status):
        status, html = fetch_playwright(url)
    return extract_vacancy_card(html, vacancy_id)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="superjob.ru Playwright+httpx scraper")
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    args = parser.parse_args()

    headless = args.headless == "true"
    result = run_verification(headless=headless)

    print("\n=== FINAL SUMMARY ===")
    print(f"Best method:       {result.get('best_method', 'BLOCKED')}")
    print(f"Vacancies found:   {result.get('vacancies_found', 0)}")
    print(f"Anti-bot reality:  {result.get('antibot_reality', 'unknown')}")
    print(f"Card extracted:    {'YES' if result.get('vacancy_card_sample') else 'NO'}")
    print()
    print("Attempt results:")
    for a in result.get("attempts", []):
        status_str = "BLOCKED" if a.get("blocked") else "OK"
        print(f"  [{a['method']}] HTTP {a['status']} → {status_str}")
