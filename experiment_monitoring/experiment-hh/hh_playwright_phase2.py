"""
hh_playwright_phase2.py -- Load live vacancy card + employer page, extract all fields.

Uses the confirmed working config: headless + stealth + direct.
Targets:
  - Vacancy 133370105 (ML-razrabotchik CV) - live, from search results
  - Employer 4563362 (ANO CISM)

Saves HTML + screenshot + extracted JSON to experiment-hh/samples/playwright/
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES_DIR = Path(__file__).parent / "samples" / "playwright"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}


def make_context(pw, headless=True, proxy=None):
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
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    }
    if proxy:
        launch_kwargs["proxy"] = proxy

    browser = pw.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        viewport=VIEWPORT,
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        user_agent=CHROME_UA,
        extra_http_headers={
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context


def navigate_and_save(context, url, html_name, ss_name, wait_s=10):
    page = context.new_page()
    print(f"  -> {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=40000)
    time.sleep(wait_s)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass

    html = page.content()
    title = page.title()
    print(f"     Title: {title!r}  HTML: {len(html)} bytes")

    (SAMPLES_DIR / html_name).write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(SAMPLES_DIR / ss_name), full_page=False)
        print(f"     Screenshot: {ss_name}")
    except Exception as e:
        print(f"     Screenshot failed: {e}")

    page.close()
    return html, title


# ---------------------------------------------------------------------------
# Extract from live vacancy card
# ---------------------------------------------------------------------------

def extract_vacancy_dom(page) -> dict:
    """Use Playwright DOM queries to extract vacancy fields."""
    result = {}

    def q(sel):
        try:
            el = page.query_selector(sel)
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    result["title"] = q("[data-qa='vacancy-title']") or q("h1")
    result["company"] = q("[data-qa='vacancy-company-name']") or q("[data-qa='employer-name']")
    # Salary: try multiple selectors
    result["salary"] = (
        q("[data-qa='vacancy-salary']")
        or q("[data-qa='vacancy-salary-compensation-type-net']")
        or ""
    )
    result["area"] = q("[data-qa='vacancy-view-location']") or q("[data-qa='vacancy-serp__vacancy-address']")
    result["experience"] = q("[data-qa='vacancy-experience']")
    result["schedule"] = q("[data-qa='vacancy-schedule']") or q("[data-qa='work-schedule']")

    # Publication date
    result["publication_date"] = q("[data-qa='vacancy-creation-time-title']") or q("time")

    # Description
    desc_el = page.query_selector("[data-qa='vacancy-description']")
    if desc_el:
        desc = desc_el.inner_text().strip()
        result["description_length"] = len(desc)
        result["description_preview"] = desc[:600]
    else:
        result["description_length"] = 0
        result["description_preview"] = ""

    # Key skills
    skills = []
    for sel in ["[data-qa='skills-element']", "[data-qa='bloko-tag__text']", "[class*='keySkill']"]:
        els = page.query_selector_all(sel)
        if els:
            skills = [el.inner_text().strip() for el in els]
            break
    result["key_skills"] = skills

    # Contacts
    contacts_el = page.query_selector("[data-qa='vacancy-contacts']")
    result["contacts_shown"] = contacts_el is not None
    result["contacts_text"] = contacts_el.inner_text().strip()[:300] if contacts_el else ""

    return result


def extract_employer_dom(page) -> dict:
    """Use Playwright DOM queries to extract employer fields."""
    result = {}

    def q(sel):
        try:
            el = page.query_selector(sel)
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    result["company_name"] = q("[data-qa='employer-name']") or q("h1")
    result["description_length"] = 0
    result["description_preview"] = ""

    # Description
    for sel in ["[data-qa='employer-description']", ".company-description", "[class*='description']"]:
        el = page.query_selector(sel)
        if el:
            desc = el.inner_text().strip()
            result["description_length"] = len(desc)
            result["description_preview"] = desc[:600]
            break

    # Open vacancies count
    result["open_vacancies"] = q("[data-qa='employer-vacancies-count']") or q("a[data-qa*='vacancy']")
    # Look for vacancies count in any link
    for sel in ["a[href*='/vacancies']", "[class*='vacancy']"]:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if any(c.isdigit() for c in text):
                result["open_vacancies_link_text"] = text[:100]
                break

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    results = {}

    with sync_playwright() as pw:
        browser, context = make_context(pw, headless=True)

        # --- Phase 1: Live vacancy card ---
        print("\n=== Live vacancy card ===")
        VACANCY_ID = "133370105"  # ML-razrabotchik (CV) - confirmed in search results
        vacancy_url = f"https://hh.ru/vacancy/{VACANCY_ID}"
        html, title = navigate_and_save(
            context,
            vacancy_url,
            f"04_live_vacancy_{VACANCY_ID}.html",
            f"04_live_vacancy_{VACANCY_ID}.png",
            wait_s=10,
        )

        # Now open a new page for DOM extraction
        page = context.new_page()
        page.goto(vacancy_url, wait_until="domcontentloaded", timeout=40000)
        time.sleep(10)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        vacancy_data = extract_vacancy_dom(page)
        page.close()

        print(f"  Vacancy extracted: {json.dumps(vacancy_data, ensure_ascii=False)[:600]}")
        results["vacancy"] = {
            "id": VACANCY_ID,
            "url": vacancy_url,
            "title_from_page_title": title,
            "extracted": vacancy_data,
        }

        # --- Phase 2: Employer page ---
        print("\n=== Employer page ===")
        EMPLOYER_ID = "4563362"  # ANO CISM (employer of ML vacancy)
        employer_url = f"https://hh.ru/employer/{EMPLOYER_ID}"
        html, title = navigate_and_save(
            context,
            employer_url,
            f"05_employer_{EMPLOYER_ID}.html",
            f"05_employer_{EMPLOYER_ID}.png",
            wait_s=8,
        )

        page = context.new_page()
        page.goto(employer_url, wait_until="domcontentloaded", timeout=40000)
        time.sleep(8)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass

        employer_data = extract_employer_dom(page)
        page.close()

        print(f"  Employer extracted: {json.dumps(employer_data, ensure_ascii=False)[:400]}")
        results["employer"] = {
            "id": EMPLOYER_ID,
            "url": employer_url,
            "title_from_page_title": title,
            "extracted": employer_data,
        }

        browser.close()

    # Also do a quick HTML-parse of the employer page for additional attributes
    employer_html_path = SAMPLES_DIR / f"05_employer_{EMPLOYER_ID}.html"
    if employer_html_path.exists():
        emp_html = employer_html_path.read_text(encoding="utf-8")
        attrs = list(set(re.findall(r'data-qa="([^"]+)"', emp_html)))
        results["employer"]["data_qa_attrs"] = sorted(attrs)
        print(f"  Employer data-qa attrs: {sorted(attrs)}")

        # Also check the vacancy page HTML for additional attributes
    vacancy_html_path = SAMPLES_DIR / f"04_live_vacancy_{VACANCY_ID}.html"
    if vacancy_html_path.exists():
        vac_html = vacancy_html_path.read_text(encoding="utf-8")
        attrs = sorted(set(re.findall(r'data-qa="([^"]+)"', vac_html)))
        results["vacancy"]["data_qa_attrs"] = attrs
        # Check for key_skills specifically
        skill_matches = re.findall(r'data-qa="([^"]*skill[^"]*)"', vac_html)
        print(f"  Vacancy skill-related data-qa: {skill_matches}")
        # Check description
        desc_matches = re.findall(r'data-qa="([^"]*desc[^"]*)"', vac_html)
        print(f"  Vacancy description-related data-qa: {desc_matches}")
        # Check contacts
        contact_matches = re.findall(r'data-qa="([^"]*contact[^"]*)"', vac_html)
        print(f"  Vacancy contact-related data-qa: {contact_matches}")

    # Save results
    out_path = SAMPLES_DIR / "phase2_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved: {out_path}")

    return results


if __name__ == "__main__":
    main()
