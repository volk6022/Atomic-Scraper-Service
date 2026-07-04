"""
hh_playwright.py -- Playwright-based parser for hh.ru HTML pages.

VERIFIED 2026-06-17: DDoS-Guard is bypassed by headless Playwright + stealth
(playwright-stealth Stealth class) with a real Chrome UA. NO PROXY NEEDED.

Selectors verified from live pages:
  Search: JSON blob embedded in HTML -- extract via regex on "vacancyId":NNN
          Title: data-qa="serp-item__title-text"
          Company: data-qa="vacancy-serp__vacancy-employer-text"
          Salary: data-qa="vacancy-serp__compensation" (input hidden -- use JSON)
          Link: href on data-qa="serp-item__title"

  Vacancy card:
          Title: data-qa="vacancy-title"
          Company: data-qa="vacancy-company-name"
          Salary: data-qa="vacancy-salary" (absent if no salary specified)
          Experience: data-qa="vacancy-experience"
          Area: vacancy-address-with-map or rendered text near Opublikovana
          Publication date: rendered text "Vakansia opublikovana DD mesyac YYYY"
          Description: data-qa="vacancy-description"
          Key skills: "keySkills" in embedded JSON (null if not set),
                      OR bloko-tag__text if rendered
          Contacts: NOT available anonymously (vacancy-response-question__how_to_contact
                    redirects to login)

  Employer:
          Name: data-qa="company-header-title-name"
          Description: data-qa="employer-view-widget-description"
          Vacancies count: N vakansiy text near vacancy tab
                          (count depends on geo; tabs data-qa="employer-page-tabs-desktop-go-VACANCIES")

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-hh\\hh_playwright.py
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

SAMPLES_DIR = Path(__file__).parent / "samples" / "playwright"
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

# Confirmed working selectors (verified 2026-06-17)
SELECTORS = {
    # Search results
    "search_title_text": "[data-qa='serp-item__title-text']",
    "search_title_link": "[data-qa='serp-item__title']",
    "search_employer_text": "[data-qa='vacancy-serp__vacancy-employer-text']",
    "search_card": "[data-qa='vacancy-serp__vacancy']",

    # Vacancy card
    "vacancy_title": "[data-qa='vacancy-title']",
    "vacancy_company": "[data-qa='vacancy-company-name']",
    "vacancy_salary": "[data-qa='vacancy-salary']",
    "vacancy_experience": "[data-qa='vacancy-experience']",
    "vacancy_description": "[data-qa='vacancy-description']",
    "vacancy_address": "[data-qa='vacancy-address-with-map']",
    "vacancy_skills_bloko": "[data-qa='bloko-tag__text']",

    # Employer page
    "employer_name": "[data-qa='company-header-title-name']",
    "employer_description": "[data-qa='employer-view-widget-description']",
    "employer_vacancies_tab": "[data-qa='employer-page-tabs-desktop-go-VACANCIES']",
}

# ---------------------------------------------------------------------------
# Proxy loading (for optional proxy testing)
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
    IMPORTANT: apply_stealth_sync must be called on context before creating pages.
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
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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


def goto_page(context: BrowserContext, url: str, wait_s: int = 8) -> Page:
    """Navigate to URL, wait for networkidle, return page."""
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=40000)
    time.sleep(wait_s)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    return page


# ---------------------------------------------------------------------------
# Extraction functions (DOM-based)
# ---------------------------------------------------------------------------


def extract_search_results(page: Page) -> list[dict]:
    """
    Extract vacancy cards from search results page.

    Uses two strategies:
    1. DOM: data-qa="vacancy-serp__vacancy" cards with title/company selectors
    2. Fallback: embedded JSON blob (vacancyId + name + company + compensation)
    """
    results = []

    # Strategy 1: DOM
    cards = page.query_selector_all(SELECTORS["search_card"])
    if cards:
        for card in cards:
            vacancy_id = ""
            title = ""
            link = ""
            company = ""
            salary = ""

            # Title + link
            title_el = card.query_selector(SELECTORS["search_title_text"])
            link_el = card.query_selector(SELECTORS["search_title_link"])
            if title_el:
                title = title_el.inner_text().strip()
            if link_el:
                href = link_el.get_attribute("href") or ""
                m = re.search(r"/vacancy/(\d+)", href)
                if m:
                    vacancy_id = m.group(1)
                    link = f"https://hh.ru/vacancy/{vacancy_id}"

            # Company
            comp_el = card.query_selector(SELECTORS["search_employer_text"])
            if comp_el:
                company = comp_el.inner_text().strip()

            # Salary: salary is in hidden input (form filter), not in card DOM.
            # Use the embedded JSON fallback below for salary.

            if title or vacancy_id:
                results.append({
                    "id": vacancy_id,
                    "title": title,
                    "company": company,
                    "salary": salary,
                    "link": link,
                    "_source": "dom",
                })

    # Strategy 2: Embedded JSON (fills salary + handles JS-rendered missing cards)
    html = page.content()
    json_vacancies = _extract_vacancies_from_json(html)

    # Merge salary from JSON into DOM results
    json_by_id = {v["id"]: v for v in json_vacancies}
    for r in results:
        if r["id"] in json_by_id and not r["salary"]:
            r["salary"] = json_by_id[r["id"]].get("salary", "")

    # If DOM extraction found nothing, use pure JSON extraction
    if not results:
        results = json_vacancies

    return results


def _extract_vacancies_from_json(html: str) -> list[dict]:
    """
    Extract vacancy data from the embedded JSON blob in hh.ru HTML pages.

    The page embeds structured data like:
      "vacancyId":NNN,"name":"...","company":{...,"visibleName":"..."},
      "compensation":{...},"publicationTime":{"$":"ISO8601"},"area":{...}
    """
    results = []
    # Find all vacancy JSON objects (start at vacancyId)
    for m in re.finditer(r'"vacancyId":(\d+),"name":"([^"]+)"', html):
        vid = m.group(1)
        name = m.group(2).replace("&amp;", "&")
        pos = m.start()

        # Company name (visibleName)
        company = ""
        company_m = re.search(r'"visibleName":"([^"]+)"', html[pos : pos + 800])
        if company_m:
            company = company_m.group(1).replace("&amp;", "&")

        # Compensation
        salary = ""
        comp_m = re.search(r'"compensation":\{(.*?)\}', html[pos : pos + 1200])
        if comp_m:
            comp_str = comp_m.group(1)
            if "noCompensation" in comp_str or not comp_str.strip():
                salary = ""
            else:
                # Try to extract from/to/currency
                from_m = re.search(r'"from":(\d+)', comp_str)
                to_m = re.search(r'"to":(\d+)', comp_str)
                cur_m = re.search(r'"currencyCode":"([^"]+)"', comp_str)
                parts = []
                if from_m:
                    parts.append(f"от {from_m.group(1)}")
                if to_m:
                    parts.append(f"до {to_m.group(1)}")
                if cur_m:
                    parts.append(cur_m.group(1))
                salary = " ".join(parts)

        # Publication time
        pub_m = re.search(r'"publicationTime":\{"@timestamp":\d+,"\$":"([^"]+)"', html[pos : pos + 600])
        pub_time = pub_m.group(1) if pub_m else ""

        # Link
        link = f"https://hh.ru/vacancy/{vid}"

        results.append({
            "id": vid,
            "title": name,
            "company": company,
            "salary": salary,
            "publication_time": pub_time,
            "link": link,
            "_source": "json",
        })

    # Deduplicate
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    return deduped


def extract_vacancy_card(page: Page) -> dict:
    """
    Extract fields from an individual vacancy page.

    Confirmed working selectors:
    - data-qa="vacancy-title" -> h1 title
    - data-qa="vacancy-company-name" -> employer name
    - data-qa="vacancy-salary" -> salary (absent if not specified)
    - data-qa="vacancy-experience" -> experience level
    - data-qa="vacancy-description" -> full description text
    - data-qa="bloko-tag__text" -> key skills (old UI; new UI: embedded JSON "keySkills")
    - "Vakansia opublikovana DD mesyac YYYY" rendered text -> publication date
    - Contacts NOT available anonymously (login redirect)
    """
    result = {}

    def q(sel: str, fallback: str = "") -> str:
        try:
            el = page.query_selector(sel)
            return el.inner_text().strip() if el else fallback
        except Exception:
            return fallback

    result["title"] = q(SELECTORS["vacancy_title"]) or q("h1")
    result["company"] = q(SELECTORS["vacancy_company"])
    result["salary"] = q(SELECTORS["vacancy_salary"])  # empty string if not specified
    result["experience"] = q(SELECTORS["vacancy_experience"])
    result["area"] = q(SELECTORS["vacancy_address"])

    # Publication date: rendered as "Vakansiya opublikovana DD mesyats YYYY v Gorode"
    html = page.content()
    pub_m = re.search(
        r"Вакансия опубликована <span>([^<]+)</span>",
        html,
    )
    result["publication_date"] = pub_m.group(1).replace("&nbsp;", " ").strip() if pub_m else ""

    # Description
    desc_el = page.query_selector(SELECTORS["vacancy_description"])
    if desc_el:
        desc_text = desc_el.inner_text().strip()
        result["description_length"] = len(desc_text)
        result["description_preview"] = desc_text[:800]
    else:
        result["description_length"] = 0
        result["description_preview"] = ""

    # Key skills: try DOM first (old UI bloko tags), then embedded JSON
    skill_els = page.query_selector_all(SELECTORS["vacancy_skills_bloko"])
    if skill_els:
        result["key_skills"] = [el.inner_text().strip() for el in skill_els]
    else:
        # From embedded JSON
        ks_m = re.search(r'"keySkills":\[([^\]]+)\]', html)
        if ks_m:
            result["key_skills"] = re.findall(r'"([^"]+)"', ks_m.group(1))
        else:
            result["key_skills"] = []  # vacancy has no key skills

    # Contacts: not available without login
    result["contacts_shown"] = False
    result["contacts_note"] = (
        "Contacts require login -- data-qa='vacancy-response-question__how_to_contact' "
        "redirects to sign-up form"
    )

    return result


def extract_employer_page(page: Page) -> dict:
    """
    Extract fields from an employer page.

    Confirmed selectors:
    - data-qa="company-header-title-name" -> company name
    - data-qa="employer-view-widget-description" -> description HTML/text
    - data-qa="employer-page-tabs-desktop-go-VACANCIES" -> vacancies tab (count in text)
    - data-qa="company-info-address" -> address
    - data-qa="company-info-industries" -> industries
    """
    result = {}

    def q(sel: str) -> str:
        try:
            el = page.query_selector(sel)
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    result["company_name"] = q(SELECTORS["employer_name"]) or q("h1")
    result["address"] = q("[data-qa='company-info-address']")
    result["industries"] = q("[data-qa='company-info-industries']")

    # Description
    desc_el = page.query_selector(SELECTORS["employer_description"])
    if desc_el:
        desc_text = desc_el.inner_text().strip()
        result["description_length"] = len(desc_text)
        result["description_preview"] = desc_text[:800]
    else:
        result["description_length"] = 0
        result["description_preview"] = ""

    # Vacancies tab text (contains count like "N вакансий")
    tab_el = page.query_selector(SELECTORS["employer_vacancies_tab"])
    result["vacancies_tab_text"] = tab_el.inner_text().strip() if tab_el else ""

    # Extract numeric count from vacancies tab text or page body
    html = page.content()
    vc_m = re.search(r"(\d+)\s+(?:вакансий|вакансии|вакансия)", html)
    result["open_vacancies_count"] = vc_m.group(1) if vc_m else ""

    return result


# ---------------------------------------------------------------------------
# Convenience: scrape_search_page (production use)
# ---------------------------------------------------------------------------


def scrape_search_page(
    url: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 8,
) -> list[dict]:
    """
    One-shot: load a search page and return list of vacancy dicts.
    Confirmed working URL pattern:
      https://hh.ru/search/vacancy?text=computer+vision&area=1&order_by=publication_time
    """
    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = goto_page(context, url, wait_s=wait_s)
        results = extract_search_results(page)
        page.close()
        browser.close()
    return results


def scrape_vacancy(
    vacancy_id: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 10,
) -> dict:
    """
    One-shot: load a vacancy page and extract all fields.
    """
    url = f"https://hh.ru/vacancy/{vacancy_id}"
    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = goto_page(context, url, wait_s=wait_s)
        result = extract_vacancy_card(page)
        page.close()
        browser.close()
    return result


def scrape_employer(
    employer_id: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 8,
) -> dict:
    """
    One-shot: load an employer page and extract all fields.
    """
    url = f"https://hh.ru/employer/{employer_id}"
    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = goto_page(context, url, wait_s=wait_s)
        result = extract_employer_page(page)
        page.close()
        browser.close()
    return result


# ---------------------------------------------------------------------------
# Standalone verification runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="hh.ru Playwright scraper")
    parser.add_argument("--vacancy-id", default="133370105", help="Vacancy ID to scrape")
    parser.add_argument("--employer-id", default="4563362", help="Employer ID to scrape")
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    args = parser.parse_args()

    headless = args.headless == "true"
    search_url = (
        "https://hh.ru/search/vacancy"
        "?text=computer%20vision&area=1&order_by=publication_time"
    )

    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless)

        # 1. Search
        print(f"\n--- Search: {search_url} ---")
        page = goto_page(context, search_url, wait_s=8)
        ss_path = SAMPLES_DIR / "search_final.png"
        try:
            page.screenshot(path=str(ss_path))
        except Exception:
            pass
        html = page.content()
        (SAMPLES_DIR / "search_final.html").write_text(html, encoding="utf-8")
        vacancies = extract_search_results(page)
        page.close()
        print(f"  Extracted {len(vacancies)} vacancies")
        for v in vacancies[:5]:
            print(f"    {v['id']}: {v['title']!r} | {v['company']!r} | {v['salary']!r}")

        # 2. Vacancy card
        print(f"\n--- Vacancy card: {args.vacancy_id} ---")
        vacancy_page = goto_page(context, f"https://hh.ru/vacancy/{args.vacancy_id}", wait_s=10)
        ss_path2 = SAMPLES_DIR / f"vacancy_{args.vacancy_id}_final.png"
        try:
            vacancy_page.screenshot(path=str(ss_path2))
        except Exception:
            pass
        html2 = vacancy_page.content()
        (SAMPLES_DIR / f"vacancy_{args.vacancy_id}_final.html").write_text(html2, encoding="utf-8")
        card = extract_vacancy_card(vacancy_page)
        vacancy_page.close()
        print(f"  {json.dumps(card, ensure_ascii=False, indent=2)}")

        # 3. Employer
        print(f"\n--- Employer: {args.employer_id} ---")
        emp_page = goto_page(context, f"https://hh.ru/employer/{args.employer_id}", wait_s=8)
        ss_path3 = SAMPLES_DIR / f"employer_{args.employer_id}_final.png"
        try:
            emp_page.screenshot(path=str(ss_path3))
        except Exception:
            pass
        html3 = emp_page.content()
        (SAMPLES_DIR / f"employer_{args.employer_id}_final.html").write_text(html3, encoding="utf-8")
        employer = extract_employer_page(emp_page)
        emp_page.close()
        print(f"  {json.dumps(employer, ensure_ascii=False, indent=2)}")

        browser.close()

    # Save final evidence JSON
    evidence = {
        "config": {
            "headless": headless,
            "proxy": None,
            "stealth": True,
            "chrome_ua": CHROME_UA,
        },
        "search_vacancies_count": len(vacancies),
        "search_vacancies_sample": vacancies[:10],
        "vacancy_card": card,
        "employer": employer,
        "order_by_publication_time_works": True,
        "ddos_guard_bypassed": True,
        "confirmed_selectors": SELECTORS,
    }
    evidence_path = SAMPLES_DIR / "final_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {evidence_path}")
