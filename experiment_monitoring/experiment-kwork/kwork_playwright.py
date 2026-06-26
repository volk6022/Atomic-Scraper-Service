"""
kwork_playwright.py — Playwright+stealth verifier for kwork.ru (ANONYMOUS ONLY).

Tests (c)+(d)+(e):
  (c) headless Playwright+stealth DIRECT
  (d) headless Playwright+stealth via RU proxy
  (e) headed Playwright+stealth DIRECT (if (c) blocked)

Verification tasks:
  1. Is https://kwork.ru/projects reachable anonymously?
  2. Anti-bot: Cloudflare vs DDoS-Guard? Does stealth bypass it?
  3. Capture all XHR/Fetch network requests — any anonymous JSON list endpoint?
  4. Are project cards visible in the HTML? Category IDs? Budget?
  5. Visit one project card /projects/{id}/view — what's visible anonymously?
  6. Robots.txt full text
  7. Screenshot + HTML saved to samples/playwright/

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-kwork\\kwork_playwright.py [--headless false]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, Request, Response, sync_playwright
from playwright_stealth import Stealth

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
SAMPLES_DIR = Path(__file__).parent / "samples" / "playwright"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

PROXIES_FILE = Path(__file__).parent.parent / "proxies.txt"

TARGET_URL = "https://kwork.ru/projects"
ROBOTS_URL = "https://kwork.ru/robots.txt"

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

# ---------------------------------------------------------------------------


def load_proxy_list() -> list[dict]:
    _LINE_RE = re.compile(
        r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
    )
    proxies = []
    if not PROXIES_FILE.exists():
        return proxies
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


def make_stealth_context(pw, headless: bool = True, proxy: Optional[dict] = None):
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
# Network capture
# ---------------------------------------------------------------------------


def setup_network_capture(page: Page) -> list[dict]:
    """Attach request/response listeners and return the shared log list."""
    xhr_log: list[dict] = []

    def on_request(req: Request) -> None:
        rt = req.resource_type
        if rt in ("xhr", "fetch"):
            xhr_log.append({
                "type": rt,
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data,
            })

    def on_response(resp: Response) -> None:
        url = resp.url
        # Capture JSON responses from kwork domains
        ct = resp.headers.get("content-type", "")
        if ("kwork.ru" in url) and ("json" in ct or "javascript" in ct):
            rt = resp.request.resource_type
            if rt in ("xhr", "fetch", "document"):
                body_preview = ""
                try:
                    body_preview = resp.text()[:2000]
                except Exception:
                    pass
                for entry in xhr_log:
                    if entry["url"] == url:
                        entry["response_content_type"] = ct
                        entry["response_status"] = resp.status
                        entry["response_body_preview"] = body_preview
                        break
                else:
                    xhr_log.append({
                        "type": rt,
                        "method": resp.request.method,
                        "url": url,
                        "response_content_type": ct,
                        "response_status": resp.status,
                        "response_body_preview": body_preview,
                    })

    page.on("request", on_request)
    page.on("response", on_response)
    return xhr_log


# ---------------------------------------------------------------------------
# Anti-bot detection
# ---------------------------------------------------------------------------


def detect_antibot_html(html: str, page: Page) -> dict:
    title = ""
    try:
        title = page.title()
    except Exception:
        pass

    result = {
        "page_title": title,
        "html_length": len(html),
        "cloudflare": "cloudflare" in html.lower() or "cf-ray" in html.lower(),
        "turnstile": "turnstile" in html.lower() or "cf-turnstile" in html.lower(),
        "ddos_guard": "ddos-guard" in html.lower(),
        "js_challenge": (
            "__cf_chl" in html
            or "cf_chl_prog" in html
            or "challenge-platform" in html
            or "jschl_vc" in html
        ),
        "real_page": (
            len(html) > 5000
            and ("kwork" in html.lower())
            and (
                "projects" in html.lower()
                or "проект" in html.lower()
                or "want" in html.lower()
            )
        ),
        "project_count_hint": 0,
    }

    # Count project ID patterns
    # kwork projects have IDs in URLs like /projects/NNNNNN/view
    project_ids = re.findall(r'/projects/(\d{4,})/view', html)
    result["project_count_hint"] = len(set(project_ids))
    result["sample_project_ids"] = list(set(project_ids))[:10]

    # Check for category filter elements
    result["category_filter_present"] = (
        "categor" in html.lower()
        and ("filter" in html.lower() or "catId" in html or "categoryId" in html)
    )

    # Check for JSON data blobs
    json_blobs = re.findall(r'window\.__([A-Z_]+)\s*=\s*(\{[^;]{20,200})', html)
    result["window_globals"] = [f"window.__{k}" for k, _ in json_blobs[:10]]

    # Inline JSON that might have project list
    inline_json = re.findall(r'"want_id"\s*:\s*(\d+)', html)
    if inline_json:
        result["want_ids_inline"] = inline_json[:10]

    return result


# ---------------------------------------------------------------------------
# Extract project cards from HTML
# ---------------------------------------------------------------------------


def extract_projects_from_html(html: str) -> list[dict]:
    """
    Try multiple patterns to extract project info from the listing HTML.
    """
    projects = []

    # Pattern 1: /projects/{id}/view links
    for m in re.finditer(r'href=["\']?/projects/(\d+)/view["\']?[^>]*>([^<]{5,200})', html):
        projects.append({
            "want_id": m.group(1),
            "title_raw": m.group(2).strip(),
            "_pattern": "href_anchor",
        })

    # Pattern 2: want_id in JSON blobs
    if not projects:
        for m in re.finditer(r'"want_id"\s*:\s*(\d+)[,}]', html):
            pid = m.group(1)
            # Try to find title near this point
            start = max(0, m.start() - 50)
            end = min(len(html), m.end() + 300)
            snippet = html[start:end]
            title_m = re.search(r'"(?:name|title)"\s*:\s*"([^"]{3,200})"', snippet)
            title = title_m.group(1) if title_m else ""
            projects.append({
                "want_id": pid,
                "title_raw": title,
                "_pattern": "json_want_id",
            })

    # Pattern 3: data-id attributes on project containers
    if not projects:
        for m in re.finditer(r'data-id=["\'](\d{4,})["\']', html):
            projects.append({
                "want_id": m.group(1),
                "title_raw": "",
                "_pattern": "data_id_attr",
            })

    # Deduplicate by want_id
    seen = set()
    deduped = []
    for p in projects:
        if p["want_id"] not in seen:
            seen.add(p["want_id"])
            deduped.append(p)

    return deduped


# ---------------------------------------------------------------------------
# Main probe
# ---------------------------------------------------------------------------


def run_probe(
    headless: bool = True,
    proxy: Optional[dict] = None,
    suffix: str = "",
) -> dict:
    label = f"headless={headless} proxy={'yes' if proxy else 'no'}{suffix}"
    print(f"\n{'='*60}")
    print(f"[Playwright] {label}")
    print(f"{'='*60}")

    evidence: dict = {
        "mode": label,
        "headless": headless,
        "proxy": proxy.get("server") if proxy else None,
    }

    with sync_playwright() as pw:
        browser, context = make_stealth_context(pw, headless=headless, proxy=proxy)

        # --- 1. robots.txt ---
        print(f"  Fetching robots.txt...")
        p_robots = context.new_page()
        xhr_robots = setup_network_capture(p_robots)
        try:
            p_robots.goto(ROBOTS_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            robots_text = p_robots.content()
            (SAMPLES_DIR / f"robots{suffix}.txt").write_text(robots_text, encoding="utf-8")
            evidence["robots_length"] = len(robots_text)
            evidence["robots_projects_disallow"] = "projects" in robots_text.lower()
            evidence["robots_page_disallow"] = "?page=" in robots_text or "&page=" in robots_text
            print(f"    robots.txt: {len(robots_text)} chars  page_disallow={evidence['robots_page_disallow']}")
        except Exception as exc:
            print(f"    robots.txt ERROR: {exc}")
            evidence["robots_error"] = str(exc)
        finally:
            p_robots.close()

        # --- 2. Main projects listing ---
        print(f"  Navigating to {TARGET_URL} ...")
        page = context.new_page()
        xhr_log = setup_network_capture(page)

        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            print(f"    domcontentloaded — waiting for networkidle...")
            time.sleep(5)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(3)  # extra settle for XHR

            html = page.content()
            title = ""
            try:
                title = page.title()
            except Exception:
                pass

            print(f"    Page title: {title!r}  HTML length: {len(html)}")

            # Screenshot
            ss_path = SAMPLES_DIR / f"kwork_projects{suffix}.png"
            try:
                page.screenshot(path=str(ss_path), full_page=False)
                print(f"    Screenshot: {ss_path}")
            except Exception as exc:
                print(f"    Screenshot failed: {exc}")

            # Save HTML
            html_path = SAMPLES_DIR / f"kwork_projects{suffix}.html"
            html_path.write_text(html, encoding="utf-8")

            # Anti-bot analysis
            ab = detect_antibot_html(html, page)
            evidence["antibot"] = ab
            print(f"    cloudflare={ab['cloudflare']}  turnstile={ab['turnstile']}  ddos_guard={ab['ddos_guard']}")
            print(f"    js_challenge={ab['js_challenge']}  real_page={ab['real_page']}")
            print(f"    project_count_hint={ab['project_count_hint']}")
            if ab.get("sample_project_ids"):
                print(f"    sample_project_ids={ab['sample_project_ids'][:5]}")
            if ab.get("window_globals"):
                print(f"    window_globals={ab['window_globals']}")
            if ab.get("want_ids_inline"):
                print(f"    want_ids_inline={ab['want_ids_inline']}")

            # Extract projects
            projects = extract_projects_from_html(html)
            evidence["projects_extracted"] = len(projects)
            evidence["projects_sample"] = projects[:5]
            print(f"    Projects extracted: {len(projects)}")
            for p in projects[:3]:
                print(f"      {p['want_id']}: {p['title_raw'][:60]!r}")

            # XHR log
            evidence["xhr_requests"] = xhr_log
            print(f"    XHR/Fetch requests captured: {len(xhr_log)}")
            for x in xhr_log[:15]:
                print(f"      [{x.get('type','?')}] {x.get('method','?')} {x['url'][:100]}")
                if x.get("response_body_preview"):
                    print(f"        body_preview: {x['response_body_preview'][:200]}")

            # Check for category filter options in HTML
            cat_ids = re.findall(r'(?:category|catId|cat_id)["\s:=]+(\d+)', html)
            evidence["category_ids_found"] = list(set(cat_ids))[:20]
            if cat_ids:
                print(f"    Category IDs found in HTML: {list(set(cat_ids))[:10]}")

            # Check for pagination hints
            evidence["pagination_hints"] = {
                "page_param_in_html": "?page=" in html or "&page=" in html,
                "pagination_element": "pagination" in html.lower() or "paginator" in html.lower(),
            }

        except Exception as exc:
            print(f"    ERROR: {exc}")
            evidence["error"] = str(exc)
        finally:
            page.close()

        # --- 3. Single project card (if we have an ID) ---
        project_ids = evidence.get("antibot", {}).get("sample_project_ids", [])
        if not project_ids:
            # Try well-known IDs from the report
            project_ids = ["3016173", "2734602"]

        card_id = project_ids[0] if project_ids else "3016173"
        card_url = f"https://kwork.ru/projects/{card_id}/view"
        print(f"\n  Navigating to project card: {card_url}")
        page2 = context.new_page()
        xhr_card = setup_network_capture(page2)
        try:
            page2.goto(card_url, wait_until="domcontentloaded", timeout=40000)
            time.sleep(5)
            try:
                page2.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass

            html2 = page2.content()
            title2 = ""
            try:
                title2 = page2.title()
            except Exception:
                pass

            print(f"    Page title: {title2!r}  HTML length: {len(html2)}")

            ss_path2 = SAMPLES_DIR / f"kwork_card_{card_id}{suffix}.png"
            try:
                page2.screenshot(path=str(ss_path2))
            except Exception:
                pass

            html_path2 = SAMPLES_DIR / f"kwork_card_{card_id}{suffix}.html"
            html_path2.write_text(html2, encoding="utf-8")

            ab2 = detect_antibot_html(html2, page2)

            # What's visible anonymously on card?
            card_info: dict = {
                "url": card_url,
                "card_id": card_id,
                "page_title": title2,
                "cloudflare": ab2["cloudflare"],
                "js_challenge": ab2["js_challenge"],
                "turnstile": ab2["turnstile"],
                "real_html": ab2["real_page"],
                "html_length": len(html2),
            }

            # Try to find title h1
            try:
                h1 = page2.query_selector("h1")
                card_info["h1_text"] = h1.inner_text().strip() if h1 else ""
            except Exception:
                card_info["h1_text"] = ""

            # Check for login gate hints
            card_info["login_gate"] = (
                "войдите" in html2.lower()
                or "войти" in html2.lower()
                or "авторизуй" in html2.lower()
                or "login" in html2.lower()
            )
            card_info["budget_visible"] = (
                "₽" in html2 or "руб" in html2.lower() or "price" in html2.lower()
            )
            card_info["description_visible"] = len(html2) > 3000 and not ab2["js_challenge"]

            evidence["card_probe"] = card_info
            evidence["card_xhr"] = xhr_card

            print(f"    title={card_info['h1_text']!r}")
            print(f"    login_gate={card_info['login_gate']}  budget_visible={card_info['budget_visible']}")
            print(f"    cloudflare={card_info['cloudflare']}  js_challenge={card_info['js_challenge']}")

        except Exception as exc:
            print(f"    Card ERROR: {exc}")
            evidence["card_error"] = str(exc)
        finally:
            page2.close()

        browser.close()

    return evidence


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    parser.add_argument("--proxy", default="false", choices=["true", "false"])
    args = parser.parse_args()

    headless = args.headless == "true"
    use_proxy = args.proxy == "true"

    proxy_dict: Optional[dict] = None
    if use_proxy:
        proxies = load_proxy_list()
        if proxies:
            proxy_dict = proxies[0]
            print(f"Using proxy: {proxy_dict['server']}")
        else:
            print("No proxies available — running direct")

    suffix = ("_headed" if not headless else "") + ("_proxy" if use_proxy and proxy_dict else "")

    evidence = run_probe(headless=headless, proxy=proxy_dict, suffix=suffix)

    # Save evidence
    ev_path = SAMPLES_DIR / f"playwright_evidence{suffix}.json"
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {ev_path}")

    # Final verdict
    ab = evidence.get("antibot", {})
    print("\n=== VERDICT ===")
    if ab.get("js_challenge") or ab.get("turnstile"):
        print("  BLOCKED by JS challenge / Turnstile — headless Playwright defeated")
        if headless:
            print("  -> Try: uv run python experiment-kwork\\kwork_playwright.py --headless false")
    elif not ab.get("real_page", False) and not evidence.get("projects_extracted", 0):
        print("  PARTIAL — page loaded but no project content detected (may be redirect or thin HTML)")
    elif evidence.get("projects_extracted", 0) > 0:
        print(f"  SUCCESS — {evidence['projects_extracted']} projects extracted anonymously!")
    elif ab.get("real_page"):
        print("  PARTIAL — real page HTML received but project extraction found nothing (check selectors)")
    else:
        print("  UNKNOWN — review HTML in samples/playwright/")


if __name__ == "__main__":
    main()
