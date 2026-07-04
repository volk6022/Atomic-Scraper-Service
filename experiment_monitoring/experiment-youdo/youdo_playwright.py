"""
youdo_playwright.py — Playwright+stealth scraper for youdo.com task listings.

Strategy:
  1. Headless Playwright + stealth (bypass JS anti-bot challenge)
  2. Capture ALL XHR/fetch network requests to find JSON API endpoints
  3. Load tasks-all-opened-all, extract listing via DOM + __NEXT_DATA__
  4. Load one task card page and extract fields
  5. Try category filtering (IT/dev tasks via URL params)
  6. Attempt proxy fallback if direct is blocked

Reuses make_stealth_browser pattern from experiment-hh/hh_playwright.py.

Run from repo root:
  cd "C:\\Users\\bhunp\\Documents\\auto-monitor-ml-cv\\repos\\Atomic-Scraper-Service"
  uv run python experiment_monitoring\\experiment-youdo\\youdo_playwright.py
  uv run python experiment_monitoring\\experiment-youdo\\youdo_playwright.py --headed
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

from playwright.sync_api import Browser, BrowserContext, Page, Request, Response, sync_playwright
from playwright_stealth import Stealth

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

EXPERIMENT_DIR = Path(__file__).parent
SAMPLES_DIR = EXPERIMENT_DIR / "samples" / "playwright"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
PROXIES_FILE = EXPERIMENT_DIR.parent.parent / "proxies.txt"  # repo root

# ---------------------------------------------------------------------------
# Config (reuse hh_playwright.py pattern)
# ---------------------------------------------------------------------------

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "ru-RU"
TIMEZONE = "Europe/Moscow"

# YouDo URL patterns from robots.txt and search results
TASKS_ALL_URL = "https://youdo.com/tasks-all-opened-all"
TASKS_PAGE_PATTERN = "https://youdo.com/tasks-all-opened-all?page={page}"
# IT/dev category — need to discover the URL param from live network
FREELANCE_IT_URL = "https://freelance.youdo.com/"

# ---------------------------------------------------------------------------
# Proxy loading (copy pattern from hh_playwright.py)
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_proxy_list() -> list[dict]:
    if not PROXIES_FILE.exists():
        print(f"[!] proxies.txt not found at {PROXIES_FILE}")
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
                "username": urllib.parse.unquote(m.group("user")),
                "password": urllib.parse.unquote(m.group("password")),
            })
    return proxies


# ---------------------------------------------------------------------------
# Stealth browser factory (identical to hh_playwright.py)
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context


# ---------------------------------------------------------------------------
# Network capture helpers
# ---------------------------------------------------------------------------

captured_requests: list[dict] = []


def make_request_interceptor():
    """Returns a request handler that captures XHR/fetch requests."""
    def on_request(request: Request) -> None:
        if request.resource_type in ("xhr", "fetch"):
            captured_requests.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            })
    return on_request


def make_response_interceptor(samples_dir: Path):
    """Returns a response handler that captures XHR/fetch JSON responses."""
    def on_response(response: Response) -> None:
        if response.request.resource_type not in ("xhr", "fetch"):
            return
        url = response.url
        status = response.status
        ct = response.headers.get("content-type", "")
        if "json" not in ct and not url.endswith(".json"):
            return
        try:
            body = response.json()
            # Sanitize URL to use as filename
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", url.replace("https://", ""))[:80]
            fname = samples_dir / f"xhr_{safe_name}_{status}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump({"url": url, "status": status, "body": body}, f, ensure_ascii=False, indent=2)
            print(f"  [XHR captured] {url[:80]} -> {status} JSON saved: {fname.name}")
        except Exception:
            pass
    return on_response


# ---------------------------------------------------------------------------
# Page navigation
# ---------------------------------------------------------------------------


def goto_page(context: BrowserContext, url: str, wait_s: int = 10) -> Page:
    page = context.new_page()

    # Attach network interceptors
    page.on("request", make_request_interceptor())
    page.on("response", make_response_interceptor(SAMPLES_DIR))

    print(f"  [nav] {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=50000)
    time.sleep(wait_s)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    return page


# ---------------------------------------------------------------------------
# Extraction: tasks listing
# ---------------------------------------------------------------------------


def extract_tasks_list(page: Page) -> list[dict]:
    """
    Extract task cards from youdo.com/tasks-all-opened-all.
    Tries multiple strategies:
      1. __NEXT_DATA__ JSON blob in <script>
      2. DOM selectors (class-based since YouDo uses Next.js + CSS modules)
    """
    html = page.content()

    # Strategy 1: __NEXT_DATA__
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            nd = json.loads(m.group(1))
            tasks = _parse_next_data_tasks(nd)
            if tasks:
                print(f"  [__NEXT_DATA__] Extracted {len(tasks)} tasks")
                return tasks
        except Exception as e:
            print(f"  [__NEXT_DATA__] Parse error: {e}")

    # Strategy 2: DOM-based extraction
    # YouDo task cards typically have: task id in URL, title, price, category
    tasks_dom = []

    # Try common task card patterns
    # Look for links matching /t/NNNNNNN pattern (task URLs)
    links = page.query_selector_all("a[href*='/t/']")
    for link in links[:50]:
        href = link.get_attribute("href") or ""
        m_id = re.search(r"/t/(\d+)", href)
        if not m_id:
            continue
        task_id = m_id.group(1)
        title = link.inner_text().strip() or ""
        if not title:
            # Try parent element text
            try:
                parent = link.query_selector("..")
                title = parent.inner_text().strip()[:200] if parent else ""
            except Exception:
                pass
        if task_id and title:
            tasks_dom.append({
                "id": task_id,
                "title": title[:200],
                "url": f"https://youdo.com/t/{task_id}",
                "_source": "dom_link",
            })

    if tasks_dom:
        print(f"  [DOM links] Extracted {len(tasks_dom)} task links")

    # Strategy 3: text-based heuristic on page HTML
    task_ids = re.findall(r'href="/t/(\d+)"', html)
    task_ids_unique = list(dict.fromkeys(task_ids))  # preserve order, deduplicate
    if task_ids_unique and not tasks_dom:
        print(f"  [regex] Found {len(task_ids_unique)} task IDs in HTML")
        for tid in task_ids_unique[:30]:
            tasks_dom.append({
                "id": tid,
                "url": f"https://youdo.com/t/{tid}",
                "_source": "regex",
            })

    return tasks_dom


def _parse_next_data_tasks(nd: dict) -> list[dict]:
    """Try to extract task list from __NEXT_DATA__ structure."""
    tasks = []
    # Common Next.js structure: nd['props']['pageProps']['tasks'] or similar
    page_props = nd.get("props", {}).get("pageProps", {})
    for key in ["tasks", "taskList", "items", "data", "list", "assignments"]:
        if key in page_props:
            raw = page_props[key]
            if isinstance(raw, list):
                for item in raw:
                    tasks.append(_normalize_task(item))
                return tasks
            if isinstance(raw, dict):
                # might be {items: [...], total: N}
                inner = raw.get("items") or raw.get("list") or []
                if inner:
                    for item in inner:
                        tasks.append(_normalize_task(item))
                    return tasks
    return tasks


def _normalize_task(item: dict) -> dict:
    """Normalize a task dict from various possible field names."""
    return {
        "id": str(item.get("id") or item.get("taskId") or item.get("task_id") or ""),
        "title": str(item.get("title") or item.get("name") or item.get("description") or "")[:200],
        "budget": str(item.get("budget") or item.get("price") or item.get("reward") or ""),
        "category": str(item.get("category") or item.get("categoryId") or ""),
        "status": str(item.get("status") or ""),
        "created_at": str(item.get("createdAt") or item.get("created_at") or item.get("date") or ""),
        "location": str(item.get("location") or item.get("city") or item.get("address") or ""),
        "remote": bool(item.get("remote") or item.get("isRemote") or item.get("online")),
        "url": f"https://youdo.com/t/{item.get('id', '')}" if item.get("id") else "",
        "_source": "next_data",
        "_raw_keys": list(item.keys())[:15],
    }


# ---------------------------------------------------------------------------
# Extraction: single task card
# ---------------------------------------------------------------------------


def extract_task_card(page: Page) -> dict:
    """Extract fields from a single task page (youdo.com/t/NNNNNNN)."""
    html = page.content()
    result: dict = {"_source": "unknown"}

    # Try __NEXT_DATA__ first
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            nd = json.loads(m.group(1))
            page_props = nd.get("props", {}).get("pageProps", {})
            result["_next_data_page_props_keys"] = list(page_props.keys())[:20]
            # Look for task data
            for key in ["task", "taskData", "assignment", "order"]:
                if key in page_props:
                    task_raw = page_props[key]
                    result.update(_normalize_task(task_raw))
                    result["_source"] = f"next_data/{key}"
                    break
        except Exception as e:
            result["_next_data_error"] = str(e)

    # DOM fallback
    def q(selector: str, fallback: str = "") -> str:
        try:
            el = page.query_selector(selector)
            return el.inner_text().strip() if el else fallback
        except Exception:
            return fallback

    if not result.get("title"):
        result["title"] = q("h1") or q("[data-testid='task-title']") or ""
    if not result.get("budget"):
        # Look for price patterns
        price_m = re.search(r"(\d[\d\s]+)\s*(?:руб|₽|rub)", html, re.IGNORECASE)
        result["budget"] = price_m.group(0).strip() if price_m else ""

    # Customer info (anonymous check)
    result["customer_visible"] = bool(
        page.query_selector("[data-testid='customer']")
        or page.query_selector(".customer")
        or re.search(r"заказчик|Заказчик|customer", html)
    )

    result["html_length"] = len(html)
    result["has_next_data"] = bool(m)
    return result


# ---------------------------------------------------------------------------
# Main verification run
# ---------------------------------------------------------------------------


def run_verification(headless: bool = True, proxy: Optional[dict] = None) -> dict:
    global captured_requests
    captured_requests = []
    evidence: dict = {}

    proxies = load_proxy_list()
    proxy_label = f"{proxy['server']}" if proxy else "direct"
    print(f"\n[*] Starting Playwright verification | headless={headless} | proxy={proxy_label}")

    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)

        # ----------------------------------------------------------------
        # Step 1: Tasks listing page
        # ----------------------------------------------------------------
        print(f"\n--- Step 1: Tasks listing {TASKS_ALL_URL} ---")
        page = goto_page(context, TASKS_ALL_URL, wait_s=12)

        # Screenshot
        ss_path = SAMPLES_DIR / "tasks_all.png"
        try:
            page.screenshot(path=str(ss_path), full_page=False)
            print(f"  [screenshot] {ss_path.name}")
        except Exception as e:
            print(f"  [screenshot failed] {e}")

        # Save HTML
        html = page.content()
        (SAMPLES_DIR / "tasks_all.html").write_text(html, encoding="utf-8")

        # Check if we got the real page or anti-bot challenge
        is_challenge = len(html) < 5000 and ("exhkqyad" in html or "noscript" in html.lower() and len(html) < 3000)
        evidence["tasks_all_is_challenge"] = is_challenge
        evidence["tasks_all_html_len"] = len(html)
        evidence["tasks_all_title"] = page.title()
        print(f"  title={page.title()!r} | html_len={len(html)} | is_challenge={is_challenge}")

        # Extract __NEXT_DATA__
        nd_m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd_m:
            nd_text = nd_m.group(1)
            print(f"  [__NEXT_DATA__] found, len={len(nd_text)}")
            try:
                nd = json.loads(nd_text)
                (SAMPLES_DIR / "tasks_all_next_data.json").write_text(
                    json.dumps(nd, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                build_id = nd.get("buildId", "N/A")
                page_name = nd.get("page", "N/A")
                page_props_keys = list(nd.get("props", {}).get("pageProps", {}).keys())
                print(f"  buildId={build_id} | page={page_name}")
                print(f"  pageProps keys: {page_props_keys[:15]}")
                evidence["build_id"] = build_id
                evidence["page_name"] = page_name
                evidence["page_props_keys"] = page_props_keys
            except Exception as e:
                print(f"  [__NEXT_DATA__] JSON error: {e}")
        else:
            print("  [__NEXT_DATA__] NOT found")
            evidence["has_next_data"] = False

        # Extract tasks
        tasks = extract_tasks_list(page)
        evidence["tasks_extracted"] = len(tasks)
        evidence["tasks_sample"] = tasks[:5]
        for t in tasks[:5]:
            print(f"  task: id={t.get('id')} title={t.get('title','')[:60]!r} budget={t.get('budget','')}")

        page.close()

        # ----------------------------------------------------------------
        # Step 2: Page 2 (pagination test)
        # ----------------------------------------------------------------
        print(f"\n--- Step 2: Pagination test page=2 ---")
        page2_url = TASKS_PAGE_PATTERN.format(page=2)
        page2 = goto_page(context, page2_url, wait_s=8)
        html2 = page2.content()
        tasks2 = extract_tasks_list(page2)
        evidence["tasks_page2_extracted"] = len(tasks2)
        evidence["tasks_page2_html_len"] = len(html2)
        ids_p1 = {t.get("id") for t in tasks if t.get("id")}
        ids_p2 = {t.get("id") for t in tasks2 if t.get("id")}
        evidence["pagination_works"] = bool(ids_p2 - ids_p1) if ids_p1 and ids_p2 else None
        print(f"  page2 tasks={len(tasks2)} | pagination_works={evidence['pagination_works']}")
        page2.close()

        # ----------------------------------------------------------------
        # Step 3: Task card extraction
        # ----------------------------------------------------------------
        print(f"\n--- Step 3: Task card extraction ---")
        # Pick first task ID from listing, or use a known one
        task_id = None
        if tasks and tasks[0].get("id"):
            task_id = tasks[0]["id"]
        else:
            # Fallback: extract from HTML
            m_id = re.search(r'href="/t/(\d+)"', html)
            task_id = m_id.group(1) if m_id else None

        if task_id:
            task_url = f"https://youdo.com/t/{task_id}"
            print(f"  Loading task card: {task_url}")
            task_page = goto_page(context, task_url, wait_s=10)
            task_html = task_page.content()
            (SAMPLES_DIR / f"task_{task_id}.html").write_text(task_html, encoding="utf-8")
            try:
                task_page.screenshot(path=str(SAMPLES_DIR / f"task_{task_id}.png"))
            except Exception:
                pass
            card = extract_task_card(task_page)
            evidence["task_card"] = card
            print(f"  card: title={card.get('title','')[:60]!r}")
            print(f"        budget={card.get('budget','')!r}")
            print(f"        customer_visible={card.get('customer_visible')}")
            print(f"        has_next_data={card.get('has_next_data')}")
            task_page.close()
        else:
            print("  No task ID available to test card")
            evidence["task_card"] = None

        # ----------------------------------------------------------------
        # Step 4: Network requests summary
        # ----------------------------------------------------------------
        print(f"\n--- Step 4: Network requests captured ---")
        xhr_reqs = [r for r in captured_requests if r["resource_type"] in ("xhr", "fetch")]
        print(f"  Total XHR/fetch: {len(xhr_reqs)}")
        for r in xhr_reqs[:30]:
            print(f"  [{r['method']}] {r['url'][:100]}")

        # Find API-like endpoints
        api_requests = [r for r in xhr_reqs if any(
            p in r["url"] for p in ["/api/", "/v1/", "/v2/", "/graphql", "/rpc", "/tasks", "/search"]
        )]
        print(f"\n  API-like requests: {len(api_requests)}")
        for r in api_requests:
            print(f"    [{r['method']}] {r['url'][:120]}")

        evidence["xhr_requests_total"] = len(xhr_reqs)
        evidence["xhr_requests_api"] = [r["url"] for r in api_requests]
        evidence["xhr_requests_all"] = [{"url": r["url"], "method": r["method"]} for r in xhr_reqs[:40]]

        # ----------------------------------------------------------------
        # Step 5: Freelance subdomain (for IT/dev tasks)
        # ----------------------------------------------------------------
        print(f"\n--- Step 5: Freelance subdomain {FREELANCE_IT_URL} ---")
        fl_page = goto_page(context, FREELANCE_IT_URL, wait_s=10)
        fl_html = fl_page.content()
        fl_title = fl_page.title()
        fl_tasks = extract_tasks_list(fl_page)
        (SAMPLES_DIR / "freelance_home.html").write_text(fl_html, encoding="utf-8")
        try:
            fl_page.screenshot(path=str(SAMPLES_DIR / "freelance_home.png"))
        except Exception:
            pass
        print(f"  title={fl_title!r} | html_len={len(fl_html)} | tasks={len(fl_tasks)}")
        evidence["freelance_tasks_extracted"] = len(fl_tasks)
        evidence["freelance_title"] = fl_title
        evidence["freelance_html_len"] = len(fl_html)

        # Check for category/filter links
        fl_links = fl_page.query_selector_all("a[href]")
        fl_hrefs = [l.get_attribute("href") or "" for l in fl_links[:100]]
        cat_links = [h for h in fl_hrefs if re.search(r"(kategori|category|/it/|/razrabotka|programm|develop)", h, re.IGNORECASE)]
        print(f"  Category links: {cat_links[:10]}")
        evidence["freelance_category_links"] = cat_links[:15]

        fl_page.close()

        browser.close()

    return evidence


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouDo Playwright scraper")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode")
    parser.add_argument("--proxy-idx", type=int, default=None, help="Use proxy at index N")
    args = parser.parse_args()

    headless = not args.headed
    proxy = None

    if args.proxy_idx is not None:
        proxies = load_proxy_list()
        if proxies:
            proxy = proxies[args.proxy_idx % len(proxies)]
            print(f"[*] Using proxy: {proxy['server']}")
        else:
            print("[!] No proxies loaded")

    # Attempt 1: direct (no proxy)
    print("\n=== Attempt 1: Direct (no proxy) ===")
    evidence = run_verification(headless=headless, proxy=None)

    # If blocked, try with proxy
    if evidence.get("tasks_all_is_challenge") and not proxy:
        print("\n=== Attempt 2: With proxy ===")
        proxies = load_proxy_list()
        if proxies:
            for i, p in enumerate(proxies[:3]):
                print(f"  Trying proxy {i+1}: {p['server']}")
                evidence_proxy = run_verification(headless=headless, proxy=p)
                if not evidence_proxy.get("tasks_all_is_challenge"):
                    evidence = evidence_proxy
                    print(f"  [SUCCESS] Proxy {i+1} worked!")
                    break
                print(f"  [FAILED] Still blocked with proxy {i+1}")
        else:
            print("  [!] No proxies available")

    # Save evidence
    evidence_path = SAMPLES_DIR / "playwright_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\n[*] Evidence saved: {evidence_path}")

    # Final summary
    print("\n=== FINAL SUMMARY ===")
    print(f"  tasks_all_is_challenge: {evidence.get('tasks_all_is_challenge')}")
    print(f"  tasks_all_html_len: {evidence.get('tasks_all_html_len')}")
    print(f"  has_next_data: {'build_id' in evidence}")
    print(f"  build_id: {evidence.get('build_id', 'N/A')}")
    print(f"  tasks_extracted: {evidence.get('tasks_extracted', 0)}")
    print(f"  tasks_page2_extracted: {evidence.get('tasks_page2_extracted', 0)}")
    print(f"  pagination_works: {evidence.get('pagination_works')}")
    print(f"  task_card: {bool(evidence.get('task_card'))}")
    print(f"  xhr_requests_total: {evidence.get('xhr_requests_total', 0)}")
    print(f"  xhr_api_endpoints: {evidence.get('xhr_requests_api', [])}")
    print(f"  freelance_tasks: {evidence.get('freelance_tasks_extracted', 0)}")
    print(f"  freelance_cat_links: {evidence.get('freelance_category_links', [])[:5]}")
