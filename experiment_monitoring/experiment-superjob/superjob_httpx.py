"""
superjob_httpx.py — Phase 2 live verification for superjob.ru (httpx only).

Attempt order:
  (a) httpx direct (no proxy)
  (b) httpx via RU residential proxy

Checks:
  1. GET https://www.superjob.ru/vacancy/search/?keywords=Python
  2. Detect anti-bot (HTTP status, redirect chain, page content)
  3. If 200: extract vacancy listing (id, title, company, salary, url, date) — SSR HTML
  4. Open one vacancy card, extract fields

Run from repo root:
  uv run python experiment_monitoring/experiment-superjob/superjob_httpx.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import httpx

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

SEARCH_URL = "https://www.superjob.ru/vacancy/search/?keywords=Python&sort_by=date_updated&order=desc&page=1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
TIMEOUT = 25.0

# ---------------------------------------------------------------------------
# Proxy loading
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


def load_proxies() -> list[str]:
    import urllib.parse
    proxies: list[str] = []
    if not PROXIES_FILE.exists():
        print(f"  [warn] proxies.txt not found at {PROXIES_FILE}")
        return proxies
    for raw_line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        enc_user = urllib.parse.quote(m.group("user"), safe="")
        enc_pass = urllib.parse.quote(m.group("password"), safe="")
        proxies.append(
            f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}"
        )
    return proxies


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------

def detect_antibot(html: str, status: int) -> dict:
    """Detect anti-bot signals in the response."""
    signals = []
    if status in (403, 429, 503):
        signals.append(f"HTTP {status}")
    lower = html.lower()
    if "cloudflare" in lower or "cf-" in lower:
        signals.append("cloudflare_detected")
    if "datadome" in lower:
        signals.append("datadome_detected")
    if "turnstile" in lower:
        signals.append("cloudflare_turnstile")
    if "captcha" in lower:
        signals.append("captcha")
    if "access denied" in lower:
        signals.append("access_denied")
    if "robot" in lower:
        signals.append("robot_check")
    if "ddos" in lower or "ddos-guard" in lower:
        signals.append("ddos_guard")
    # Check if actual vacancy content is present
    if "vacancy" in lower or "вакансия" in lower or "вакансии" in lower:
        signals.append("vacancy_content_present")
    return {
        "http_status": status,
        "signals": signals,
        "blocked": any(s in signals for s in [
            f"HTTP {status}" for s in [403, 429, 503]
        ] + ["captcha", "access_denied", "robot_check", "datadome_detected"]),
        "html_length": len(html),
    }


def extract_vacancies_html(html: str) -> list[dict]:
    """
    Extract vacancy listings from superjob.ru HTML search results.

    Tries multiple patterns:
    1. data-vacancy-id attributes
    2. JSON-LD / embedded JSON
    3. Regex patterns for vacancy links
    """
    results = []

    # Strategy 1: Look for vacancy card containers with data attributes
    # Pattern: <div ... data-vacancy-id="NNN" ...>
    id_pattern = re.findall(r'data-vacancy-id=["\'](\d+)["\']', html)
    if id_pattern:
        ids_found = list(dict.fromkeys(id_pattern))  # deduplicate, preserve order
        print(f"  [html] Found {len(ids_found)} vacancy IDs via data-vacancy-id attr")
        for vid in ids_found[:20]:
            results.append({
                "id": vid,
                "title": "",
                "company": "",
                "salary": "",
                "url": f"https://www.superjob.ru/vakansii/{vid}.html",
                "date": "",
                "_source": "data-vacancy-id",
            })

    # Strategy 2: Vacancy links pattern /vakansii/NNN.html or /vacancy/NNN/
    if not results:
        link_matches = re.findall(
            r'href=["\'](?:https?://(?:www\.)?superjob\.ru)?/vakansii[^/]*/(\d+)\.html["\']',
            html,
        )
        if not link_matches:
            link_matches = re.findall(
                r'href=["\'](?:https?://(?:www\.)?superjob\.ru)?/vakansii/(\d+)[/"\'?]',
                html,
            )
        if link_matches:
            ids_found = list(dict.fromkeys(link_matches))
            print(f"  [html] Found {len(ids_found)} vacancy IDs via href pattern")
            for vid in ids_found[:20]:
                results.append({
                    "id": vid,
                    "title": "",
                    "company": "",
                    "salary": "",
                    "url": f"https://www.superjob.ru/vakansii/{vid}.html",
                    "date": "",
                    "_source": "href",
                })

    # Strategy 3: Look for embedded JSON with vacancy data
    # Common pattern: window.__initialState__ or similar
    json_match = re.search(r'window\.__(?:initialState|INITIAL_STATE|serverState)__\s*=\s*(\{.{100,}?\});', html, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            print(f"  [html] Found window state JSON ({len(json_match.group(1))} chars)")
            # Try to navigate the structure
            results.append({"_raw_window_state": "found", "_source": "window_state"})
        except Exception as e:
            print(f"  [html] window state JSON parse error: {e}")

    # Strategy 4: Search for vacancy titles near salary patterns
    if not results:
        # superjob uses structured markup
        title_salary = re.findall(
            r'"profession"\s*:\s*"([^"]+)"[^}]*?"salary_min"\s*:\s*(\d+)[^}]*?"salary_max"\s*:\s*(\d+)',
            html,
        )
        if title_salary:
            for i, (title, sal_min, sal_max) in enumerate(title_salary[:20]):
                results.append({
                    "id": str(i),
                    "title": title,
                    "company": "",
                    "salary": f"{sal_min}–{sal_max}",
                    "url": "",
                    "date": "",
                    "_source": "embedded_json_profession",
                })

    return results


def extract_vacancy_card_html(html: str, vacancy_url: str) -> dict:
    """Extract fields from a single vacancy card page."""
    result = {"url": vacancy_url}

    # Title: look for h1 or vacancy title meta
    title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if title_m:
        result["title"] = title_m.group(1).strip()

    # Meta title fallback
    meta_title = re.search(r'<title>([^<]+)</title>', html)
    if meta_title and "title" not in result:
        result["title"] = meta_title.group(1).strip()

    # Company
    company_m = re.search(r'"company"\s*:\s*\{[^}]*"title"\s*:\s*"([^"]+)"', html)
    if company_m:
        result["company"] = company_m.group(1)

    # Salary
    salary_m = re.search(r'"salary_min"\s*:\s*(\d+)[^}]*"salary_max"\s*:\s*(\d+)[^}]*"currency"\s*:\s*"([^"]+)"', html)
    if salary_m:
        result["salary"] = f"{salary_m.group(1)}–{salary_m.group(2)} {salary_m.group(3)}"

    # Date published
    date_m = re.search(r'"date_published"\s*:\s*(\d+)', html)
    if date_m:
        import datetime
        ts = int(date_m.group(1))
        result["date_published"] = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    # Town
    town_m = re.search(r'"town"\s*:\s*\{[^}]*"title"\s*:\s*"([^"]+)"', html)
    if town_m:
        result["town"] = town_m.group(1)

    # Description length
    result["html_length"] = len(html)

    # Check for login wall
    if "войти" in html.lower() and "зарегистрироваться" in html.lower() and len(html) < 5000:
        result["login_wall"] = True

    return result


# ---------------------------------------------------------------------------
# Main verification flow
# ---------------------------------------------------------------------------

def try_httpx(url: str, proxy: str | None = None, label: str = "direct") -> tuple[int, str]:
    """Fetch URL with httpx, return (status, html). Returns (-1, err) on failure."""
    try:
        kwargs: dict = {
            "headers": HEADERS,
            "timeout": TIMEOUT,
            "follow_redirects": True,
        }
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as client:
            resp = client.get(url)
            print(f"  [httpx/{label}] {resp.status_code} (redirects: {len(resp.history)}) — {url[:80]}")
            return resp.status_code, resp.text
    except Exception as exc:
        print(f"  [httpx/{label}] ERROR: {type(exc).__name__}: {exc}")
        return -1, str(exc)


def run_verification() -> dict:
    evidence: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "search_url": SEARCH_URL,
        "attempts": [],
        "best_result": None,
    }

    # --- Attempt (a): httpx direct ---
    print("\n=== Attempt (a): httpx DIRECT ===")
    status_a, html_a = try_httpx(SEARCH_URL, proxy=None, label="direct")
    antibot_a = detect_antibot(html_a, status_a)
    print(f"  Anti-bot signals: {antibot_a['signals']}")
    print(f"  HTML length: {antibot_a['html_length']}")

    attempt_a = {
        "method": "httpx_direct",
        "status": status_a,
        "antibot": antibot_a,
        "vacancies": [],
    }

    if status_a == 200 and "vacancy_content_present" in antibot_a["signals"]:
        # Save HTML
        (SAMPLES_DIR / "search_httpx_direct.html").write_text(html_a, encoding="utf-8")
        print("  Saved: samples/search_httpx_direct.html")
        vacancies = extract_vacancies_html(html_a)
        attempt_a["vacancies"] = vacancies
        print(f"  Extracted {len(vacancies)} vacancies")
        evidence["best_result"] = "httpx_direct"
    else:
        # Save partial for debugging
        (SAMPLES_DIR / "search_httpx_direct_blocked.html").write_text(html_a[:5000], encoding="utf-8")

    evidence["attempts"].append(attempt_a)

    # --- Attempt (b): httpx via RU proxy ---
    print("\n=== Attempt (b): httpx via RU proxy ===")
    proxies = load_proxies()
    if not proxies:
        print("  No proxies available; skipping proxy attempt")
    else:
        # Try up to 5 proxies
        proxy_success = False
        for i, proxy in enumerate(proxies[:5]):
            print(f"  Trying proxy #{i+1}: ...@{proxy.split('@')[-1]}")
            status_b, html_b = try_httpx(SEARCH_URL, proxy=proxy, label=f"proxy-{i+1}")
            antibot_b = detect_antibot(html_b, status_b)
            print(f"  Anti-bot signals: {antibot_b['signals']}")
            print(f"  HTML length: {antibot_b['html_length']}")

            attempt_b = {
                "method": f"httpx_proxy_{i+1}",
                "proxy_host": proxy.split("@")[-1],
                "status": status_b,
                "antibot": antibot_b,
                "vacancies": [],
            }

            if status_b == 200 and "vacancy_content_present" in antibot_b["signals"]:
                (SAMPLES_DIR / f"search_httpx_proxy{i+1}.html").write_text(html_b, encoding="utf-8")
                print(f"  Saved: samples/search_httpx_proxy{i+1}.html")
                vacancies_b = extract_vacancies_html(html_b)
                attempt_b["vacancies"] = vacancies_b
                print(f"  Extracted {len(vacancies_b)} vacancies")
                if evidence["best_result"] is None:
                    evidence["best_result"] = f"httpx_proxy_{i+1}"
                proxy_success = True
                evidence["attempts"].append(attempt_b)
                break
            else:
                evidence["attempts"].append(attempt_b)
                time.sleep(1)

        if not proxy_success:
            print("  All proxy attempts blocked/failed")

    # --- If we got vacancies, fetch one vacancy card ---
    best_vacancies = []
    for attempt in evidence["attempts"]:
        if attempt.get("vacancies"):
            best_vacancies = attempt["vacancies"]
            best_method = attempt["method"]
            break

    if best_vacancies and best_vacancies[0].get("id"):
        vid = best_vacancies[0]["id"]
        card_url = best_vacancies[0].get("url") or f"https://www.superjob.ru/vakansii/{vid}.html"
        print(f"\n=== Fetching vacancy card: {card_url} ===")
        time.sleep(2)  # polite delay
        status_card, html_card = try_httpx(card_url, proxy=None, label="card-direct")
        antibot_card = detect_antibot(html_card, status_card)
        print(f"  Anti-bot signals: {antibot_card['signals']}")

        if status_card == 200:
            (SAMPLES_DIR / f"vacancy_{vid}_httpx.html").write_text(html_card, encoding="utf-8")
            card_data = extract_vacancy_card_html(html_card, card_url)
            print(f"  Card data: {json.dumps(card_data, ensure_ascii=False, indent=2)}")
            evidence["vacancy_card_sample"] = {
                "vacancy_id": vid,
                "url": card_url,
                "antibot": antibot_card,
                "fields": card_data,
            }
        else:
            evidence["vacancy_card_sample"] = {
                "vacancy_id": vid,
                "url": card_url,
                "antibot": antibot_card,
                "fields": {},
                "error": f"HTTP {status_card}",
            }

    # --- Save evidence JSON ---
    evidence_path = SAMPLES_DIR / "httpx_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {evidence_path}")

    return evidence


if __name__ == "__main__":
    result = run_verification()
    print(f"\n=== SUMMARY ===")
    print(f"Best working method: {result.get('best_result', 'NONE — all blocked')}")
    for a in result["attempts"]:
        print(f"  [{a['method']}] HTTP {a['status']} | signals: {a['antibot']['signals']} | vacancies: {len(a.get('vacancies', []))}")
