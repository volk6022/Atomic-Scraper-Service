"""
habr_verify.py — Phase 2 live verification for Habr Career.

Attempt order:
  1. httpx direct (no proxy)
  2. httpx + rotating proxy
  3. Playwright + stealth headless direct
  4. Playwright + stealth headless + proxy
  5. Playwright + stealth headed + proxy

Targets:
  A. career.habr.com/vacancies?sort=date&page=1  — vacancy listing
  B. career.habr.com/vacancies/<id>              — vacancy card
  C. career.habr.com/vacancies/remote?sort=date&page=1  — remote/contract

Run from repo root:
  cd "C:\\Users\\bhunp\\Documents\\auto-monitor-ml-cv\\repos\\Atomic-Scraper-Service"
  uv run python experiment_monitoring\\experiment-habr\\habr_verify.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

THIS_DIR = Path(__file__).parent
SAMPLES_DIR = THIS_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

REPO_ROOT = Path(__file__).parent.parent.parent
HH_EXPERIMENT = REPO_ROOT / "experiment_monitoring" / "experiment-hh"
sys.path.insert(0, str(HH_EXPERIMENT))

from proxy_client import load_proxies, ProxyRotatingClient  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

LISTING_URL = "https://career.habr.com/vacancies?sort=date&page=1"
REMOTE_URL = "https://career.habr.com/vacancies/remote?sort=date&page=1"
FREELANCE_URL = "https://career.habr.com/vacancies?sort=date&type=all&page=1"  # includes contract

evidence: dict = {
    "attempts": [],
    "listing": None,
    "card": None,
    "remote_listing": None,
    "freelance_check": None,
}


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------


def parse_vacancy_listing(html: str) -> list[dict]:
    """Extract vacancy cards from career.habr.com HTML listing page."""
    results = []

    # Strategy 1: look for vacancy cards with data-id or href patterns
    # career.habr.com uses hrefs like /vacancies/12345-title-slug
    # Try multiple patterns

    # Pattern A: data-id attribute on vacancy item
    for m in re.finditer(r'data-id=["\'](\d+)["\']', html):
        vid = m.group(1)
        pos = m.start()

        # Look for title in surrounding context
        title = ""
        title_m = re.search(r'class="[^"]*vacancy-card__title[^"]*"[^>]*>([^<]+)<', html[pos:pos+1000])
        if not title_m:
            title_m = re.search(r'<a[^>]+href="/vacancies/\d+[^"]*"[^>]*>([^<]+)</a>', html[pos:pos+500])
        if title_m:
            title = title_m.group(1).strip()

        results.append({"id": vid, "title": title, "_source": "data-id"})

    if results:
        return _dedup(results)

    # Pattern B: vacancy links /vacancies/NNN or /vacancies/NNN-slug
    seen = set()
    for m in re.finditer(r'href=["\'](/vacancies/(\d+)[^"\']*)["\']', html):
        href = m.group(1)
        vid = m.group(2)
        if vid in seen or len(vid) < 4:
            continue
        seen.add(vid)
        pos = m.start()

        # Title: text content right after href
        title = ""
        title_m = re.search(r'href="' + re.escape(href) + r'"[^>]*>([^<]+)<', html)
        if title_m:
            title = title_m.group(1).strip()

        # Company: look nearby
        company = ""
        company_m = re.search(
            r'class="[^"]*company[^"]*"[^>]*><[^>]*>([^<]+)<',
            html[max(0, pos-200):pos+800]
        )
        if company_m:
            company = company_m.group(1).strip()

        # Salary: look nearby
        salary = ""
        sal_m = re.search(
            r'class="[^"]*salary[^"]*"[^>]*>([^<]+)<',
            html[max(0, pos-200):pos+800]
        )
        if sal_m:
            salary = re.sub(r'<[^>]+>', '', sal_m.group(1)).strip()

        results.append({
            "id": vid,
            "title": title,
            "company": company,
            "salary": salary,
            "url": f"https://career.habr.com{href}",
            "_source": "href-pattern",
        })

    return _dedup(results)


def _dedup(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        key = item.get("id", "")
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def parse_vacancy_card(html: str, url: str) -> dict:
    """Extract fields from a single vacancy page."""
    result = {"url": url}

    # Title: look for h1 or vacancy title class
    h1_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if h1_m:
        result["title"] = h1_m.group(1).strip()
    else:
        title_m = re.search(r'class="[^"]*vacancy[_-]title[^"]*"[^>]*>([^<]+)<', html)
        if title_m:
            result["title"] = title_m.group(1).strip()

    # Company
    company_m = re.search(r'class="[^"]*company[_-]name[^"]*"[^>]*>([^<]+)<', html)
    if company_m:
        result["company"] = company_m.group(1).strip()
    else:
        company_m2 = re.search(r'"company":\{"name":"([^"]+)"', html)
        if company_m2:
            result["company"] = company_m2.group(1)

    # Salary
    sal_m = re.search(r'class="[^"]*salary[^"]*"[^>]*>([^<]+)<', html)
    if sal_m:
        result["salary"] = re.sub(r'<[^>]+>', '', sal_m.group(1)).strip()

    # Skills
    skills = re.findall(r'class="[^"]*skill[^"]*"[^>]*>([^<]+)<', html)
    result["skills"] = list(set(s.strip() for s in skills if len(s.strip()) > 1))[:20]

    # Published date
    date_m = re.search(r'"published(?:At|_at|Date)":\s*"([^"]+)"', html)
    if not date_m:
        date_m = re.search(r'datetime=["\']([^"\']+)["\']', html)
    if date_m:
        result["published_at"] = date_m.group(1)

    # Description length
    desc_m = re.search(r'class="[^"]*description[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if desc_m:
        desc_text = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
        result["description_length"] = len(desc_text)
        result["description_preview"] = desc_text[:400]

    return result


# ---------------------------------------------------------------------------
# Attempt 1: httpx direct
# ---------------------------------------------------------------------------


def attempt_httpx_direct() -> tuple[bool, Optional[str], int]:
    """Try httpx without proxy. Return (success, html, status_code)."""
    print("\n[1] httpx direct (no proxy)...")
    try:
        with httpx.Client(
            headers=HEADERS,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            resp = client.get(LISTING_URL)
            print(f"  status={resp.status_code}  len={len(resp.text)}")
            if resp.status_code == 200:
                return True, resp.text, resp.status_code
            else:
                (SAMPLES_DIR / "listing_httpx_direct_fail.html").write_text(
                    resp.text, encoding="utf-8"
                )
                return False, resp.text, resp.status_code
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False, None, 0


# ---------------------------------------------------------------------------
# Attempt 2: httpx + proxy
# ---------------------------------------------------------------------------


def attempt_httpx_proxy() -> tuple[bool, Optional[str], int]:
    """Try httpx with rotating proxy."""
    print("\n[2] httpx + rotating proxy...")
    try:
        proxies = load_proxies()
        if not proxies:
            print("  No proxies loaded, skipping")
            return False, None, 0
        print(f"  Loaded {len(proxies)} proxies")
        client = ProxyRotatingClient(
            proxies=proxies,
            timeout=25.0,
            max_retries=5,
            headers=HEADERS,
        )
        resp = client.get(LISTING_URL)
        print(f"  status={resp.status_code}  len={len(resp.text)}")
        if resp.status_code == 200:
            return True, resp.text, resp.status_code
        else:
            (SAMPLES_DIR / "listing_httpx_proxy_fail.html").write_text(
                resp.text, encoding="utf-8"
            )
            return False, resp.text, resp.status_code
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False, None, 0


# ---------------------------------------------------------------------------
# Playwright helpers (reuse hh_playwright patterns)
# ---------------------------------------------------------------------------


def attempt_playwright(headless: bool = True, use_proxy: bool = False) -> tuple[bool, Optional[str], int]:
    """Try Playwright + stealth."""
    label = f"headless={headless} proxy={use_proxy}"
    print(f"\n[Playwright] {label}...")

    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError as e:
        print(f"  ImportError: {e}")
        return False, None, 0

    proxy_dict = None
    if use_proxy:
        proxies = load_proxies()
        if proxies:
            import random
            line = random.choice(proxies)
            # parse back: http://USER:PASS@HOST:PORT
            m = re.match(r"http://([^:]+):([^@]+)@([^:]+):(\d+)", line)
            if m:
                proxy_dict = {
                    "server": f"http://{m.group(3)}:{m.group(4)}",
                    "username": urllib.parse.unquote(m.group(1)),
                    "password": urllib.parse.unquote(m.group(2)),
                }

    stealth = Stealth(
        navigator_user_agent_override=CHROME_UA,
        navigator_languages_override=("ru-RU", "ru"),
        navigator_platform_override="Win32",
        navigator_vendor_override="Google Inc.",
        webgl_vendor_override="Intel Inc.",
        webgl_renderer_override="Intel Iris OpenGL Engine",
    )

    launch_kwargs = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    }
    if proxy_dict:
        launch_kwargs["proxy"] = proxy_dict

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                user_agent=CHROME_UA,
                extra_http_headers={
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
            stealth.apply_stealth_sync(context)
            page = context.new_page()
            page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            html = page.content()
            status = 200 if len(html) > 1000 else 0

            suffix = f"_{'headless' if headless else 'headed'}_{'proxy' if use_proxy else 'direct'}"
            (SAMPLES_DIR / f"listing_playwright{suffix}.html").write_text(html, encoding="utf-8")
            try:
                page.screenshot(path=str(SAMPLES_DIR / f"listing_playwright{suffix}.png"))
            except Exception:
                pass

            print(f"  html_len={len(html)}")
            browser.close()

            has_content = (
                "vacancy" in html.lower() or
                "вакансия" in html.lower() or
                "вакансии" in html.lower() or
                len(html) > 10000
            )
            return has_content, html if has_content else None, status
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False, None, 0


# ---------------------------------------------------------------------------
# Main verification flow
# ---------------------------------------------------------------------------


def run():
    print("=" * 60)
    print("Habr Career — Phase 2 Live Verification")
    print(f"Target: {LISTING_URL}")
    print("=" * 60)

    working_html = None

    # Attempt 1: httpx direct
    ok, html, code = attempt_httpx_direct()
    evidence["attempts"].append({"method": "httpx_direct", "status_code": code, "success": ok})
    if ok:
        print("  [OK] httpx direct works!")
        working_html = html
        (SAMPLES_DIR / "listing_httpx_direct.html").write_text(html, encoding="utf-8")

    # Attempt 2: httpx proxy (always try for comparison)
    if not working_html:
        ok2, html2, code2 = attempt_httpx_proxy()
        evidence["attempts"].append({"method": "httpx_proxy", "status_code": code2, "success": ok2})
        if ok2:
            print("  [OK] httpx proxy works!")
            working_html = html2
            (SAMPLES_DIR / "listing_httpx_proxy.html").write_text(html2, encoding="utf-8")

    # Attempt 3: Playwright headless direct
    if not working_html:
        ok3, html3, code3 = attempt_playwright(headless=True, use_proxy=False)
        evidence["attempts"].append({"method": "playwright_headless_direct", "status_code": code3, "success": ok3})
        if ok3:
            print("  [OK] Playwright headless direct works!")
            working_html = html3

    # Attempt 4: Playwright headless + proxy
    if not working_html:
        ok4, html4, code4 = attempt_playwright(headless=True, use_proxy=True)
        evidence["attempts"].append({"method": "playwright_headless_proxy", "status_code": code4, "success": ok4})
        if ok4:
            print("  [OK] Playwright headless + proxy works!")
            working_html = html4

    # Attempt 5: Playwright headed + proxy
    if not working_html:
        ok5, html5, code5 = attempt_playwright(headless=False, use_proxy=True)
        evidence["attempts"].append({"method": "playwright_headed_proxy", "status_code": code5, "success": ok5})
        if ok5:
            print("  [OK] Playwright headed + proxy works!")
            working_html = html5

    if not working_html:
        print("\n[BLOCKED] All attempts failed — chrome-devtools-MCP escalation needed")
        evidence["blocked"] = True
        _save_evidence()
        return

    # --- Parse listing ---
    print("\n--- Parsing vacancy listing ---")
    vacancies = parse_vacancy_listing(working_html)
    print(f"  Extracted {len(vacancies)} vacancies")
    for v in vacancies[:5]:
        print(f"    {v.get('id','?')}: {v.get('title','?')!r} | {v.get('company','?')!r} | {v.get('salary','?')!r}")
    evidence["listing"] = {
        "url": LISTING_URL,
        "vacancy_count": len(vacancies),
        "sample": vacancies[:10],
    }

    # --- Fetch and parse first vacancy card ---
    if vacancies:
        first = vacancies[0]
        card_url = first.get("url") or f"https://career.habr.com/vacancies/{first['id']}"
        print(f"\n--- Fetching vacancy card: {card_url} ---")
        card_html = None

        # Try httpx direct for card
        try:
            with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
                resp = client.get(card_url)
                print(f"  card status={resp.status_code}  len={len(resp.text)}")
                if resp.status_code == 200:
                    card_html = resp.text
                    (SAMPLES_DIR / f"card_{first['id']}_httpx.html").write_text(card_html, encoding="utf-8")
        except Exception as e:
            print(f"  card httpx error: {e}")

        if card_html:
            card = parse_vacancy_card(card_html, card_url)
            print(f"  Card: {json.dumps(card, ensure_ascii=False)[:600]}")
            evidence["card"] = card

    # --- Remote/contract listing ---
    print(f"\n--- Remote listing: {REMOTE_URL} ---")
    try:
        with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
            resp = client.get(REMOTE_URL)
            print(f"  remote status={resp.status_code}  len={len(resp.text)}")
            if resp.status_code == 200:
                remote_vacancies = parse_vacancy_listing(resp.text)
                print(f"  Remote vacancies: {len(remote_vacancies)}")
                (SAMPLES_DIR / "listing_remote_httpx.html").write_text(resp.text, encoding="utf-8")
                evidence["remote_listing"] = {
                    "url": REMOTE_URL,
                    "vacancy_count": len(remote_vacancies),
                    "sample": remote_vacancies[:5],
                }
    except Exception as e:
        print(f"  remote error: {e}")

    # --- Freelance.habr.com status check ---
    print("\n--- Checking freelance.habr.com/tasks status ---")
    try:
        with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
            resp = client.get("https://freelance.habr.com/tasks")
            print(f"  freelance status={resp.status_code}  len={len(resp.text)}")
            (SAMPLES_DIR / "freelance_tasks_check.html").write_text(resp.text, encoding="utf-8")
            evidence["freelance_check"] = {
                "url": "https://freelance.habr.com/tasks",
                "status_code": resp.status_code,
                "html_len": len(resp.text),
                "contains_closure_msg": any(
                    w in resp.text.lower()
                    for w in ["закрыт", "завершил", "прекратил", "закончил", "больше не работает", "closed"]
                ),
                "html_preview": resp.text[:500],
            }
    except Exception as e:
        print(f"  freelance check error: {e}")
        evidence["freelance_check"] = {"error": str(e)}

    _save_evidence()


def _save_evidence():
    path = SAMPLES_DIR / "habr_verification_evidence.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {path}")


if __name__ == "__main__":
    run()
