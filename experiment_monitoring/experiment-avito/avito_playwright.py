"""
avito_playwright.py — Playwright+stealth parser for avito.ru vacancies.

VERIFIED 2026-06-18: httpx direct (no proxy, no Playwright) returns HTTP 200
with FULL SSR HTML containing 50 items per page as embedded JSON in the
`window.__staticRouterHydrationData` blob. Playwright is NOT required for
the listing page; it may be needed if Avito adds JS challenges or for JS-driven
search results (q= parameter).

Architecture confirmed 2026-06-18:
  - Listing page: FULL SSR-HTML via httpx. 50 items per page.
  - Embedded JSON: window.__staticRouterHydrationData (JSON.parse double-encoded)
    → loaderData → "catalog-or-main-or-item" → catalog.items[]
    Each item: id, title, description, urlPath, priceDetailed, location,
               sortTimeStamp, allowTimeStamp, contacts, seller, images
  - Item card: window.__staticRouterHydrationData → buyerItem.item
    Full fields: id, title, description, descriptionHtml, address, price,
    formattedPrice, seller (avatar, verification), shop (id, name),
    phone (mask, publicPhone - visible anonymously!), sortFormatedDate,
    sortTimeStamp, finishTime, vacancyParams, flags, location, images
  - Sort by date: ?s=104
  - Pagination: ?s=104&p=N (N=1,2,3,...)
  - City filter: /{city_slug}/vakansii (e.g. /moskva/vakansii, /sankt-peterburg/vakansii)
  - Text search: ?q=<query>&s=104 — works but may return very few results
    (q= on listing is SSR but may use suspenseSsr lazy loading for results)
  - Total vacancies available: ~2.67M

Sort values:
  101 = default (relevance)
  104 = by date (newest first) — USE THIS for monitoring
    2 = by salary desc
    1 = by salary asc

Confirmed working URLs (2026-06-18):
  https://www.avito.ru/all/vakansii?s=104
  https://www.avito.ru/all/vakansii?s=104&p=2
  https://www.avito.ru/moskva/vakansii?s=104
  https://www.avito.ru/sankt-peterburg/vakansii?s=104
  https://www.avito.ru/all/vakansii?q=python+developer&s=104

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-avito\\avito_playwright.py
  uv run python experiment-avito\\avito_playwright.py --headless false
  uv run python experiment-avito\\avito_playwright.py --proxy-port 11000
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import datetime
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

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# ---------------------------------------------------------------------------
# Proxy loading
# ---------------------------------------------------------------------------

import urllib.parse

_LINE_RE = re.compile(
    r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_proxy_list() -> list[dict]:
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


def load_proxy_urls() -> list[str]:
    """Return httpx-compatible proxy URL strings."""
    proxies = []
    if not PROXIES_FILE.exists():
        return proxies
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            enc_user = urllib.parse.quote(m.group("user"), safe="")
            enc_pass = urllib.parse.quote(m.group("password"), safe="")
            proxies.append(f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}")
    return proxies


# ---------------------------------------------------------------------------
# Core extraction: decode staticRouterHydrationData
# ---------------------------------------------------------------------------

def decode_hydration_data(html: str) -> dict:
    """Decode window.__staticRouterHydrationData from page HTML."""
    m = re.search(
        r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);',
        html, re.DOTALL
    )
    if not m:
        return {}
    raw = m.group(1)
    try:
        decoded_str = json.loads('"' + raw + '"')
        return json.loads(decoded_str)
    except Exception:
        # Fallback manual unescape
        try:
            decoded_str = raw.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\r', '')
            return json.loads(decoded_str)
        except Exception:
            return {}


def extract_listing_items(html: str) -> list[dict]:
    """
    Extract vacancy list from listing page HTML.

    Returns list of dicts with:
      id, title, price_string, price_value, location, url,
      sort_timestamp, sort_datetime, allow_timestamp, allow_datetime,
      description_snippet, images_count, phone_visible, message_enabled

    Primary method: parse <script type="mime/invalid" data-mfe-state="true"> JSON blob.
      Path: .state → (find catalog via deep search) → catalog.items[]
    Fallback: regex extraction from raw HTML.

    VERIFIED 2026-06-18: The item list is NOT in window.__staticRouterHydrationData
    (that blob only has topBanner + buyerLocationProps for listing pages).
    The actual item data is in the MFE state script block.
    """
    items = []

    # Primary: MFE state script block
    m_mfe = re.search(
        r'<script[^>]+type=["\']mime/invalid["\'][^>]+data-mfe-state=["\']true["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if m_mfe:
        try:
            data = json.loads(m_mfe.group(1))
            state = data.get("state", {})

            def find_catalog(obj, depth=0):
                if depth > 6:
                    return None
                if isinstance(obj, dict):
                    if "catalog" in obj and isinstance(obj.get("catalog"), dict):
                        cat = obj["catalog"]
                        if "items" in cat and isinstance(cat.get("items"), list):
                            return cat
                    for v in obj.values():
                        result = find_catalog(v, depth + 1)
                        if result:
                            return result
                return None

            catalog = find_catalog(state)
            if catalog:
                raw_items = catalog.get("items", [])
                for raw in raw_items:
                    if not isinstance(raw, dict) or "id" not in raw:
                        continue
                    price = raw.get("priceDetailed") or {}
                    sort_ts = raw.get("sortTimeStamp")
                    allow_ts = raw.get("allowTimeStamp")
                    contacts = raw.get("contacts") or {}
                    url_path = raw.get("urlPath", "")
                    if "?" in url_path:
                        url_path = url_path.split("?")[0]
                    location = raw.get("location") or {}

                    items.append({
                        "id": str(raw["id"]),
                        "title": raw.get("title", ""),
                        "price_string": price.get("string", ""),
                        "price_value": price.get("value"),
                        "price_postfix": price.get("postfix", ""),
                        "price_full_string": price.get("fullString", ""),
                        "location": location.get("name", ""),
                        "url": f"https://www.avito.ru{url_path}",
                        "sort_timestamp_ms": sort_ts,
                        "sort_datetime": str(datetime.datetime.fromtimestamp(sort_ts / 1000)) if sort_ts else None,
                        "allow_timestamp_ms": allow_ts,
                        "allow_datetime": str(datetime.datetime.fromtimestamp(allow_ts / 1000)) if allow_ts else None,
                        "description_snippet": (raw.get("description") or "")[:200],
                        "images_count": raw.get("imagesCount", 0),
                        "phone_visible": contacts.get("phone", False),
                        "message_enabled": contacts.get("message", False),
                        "category": (raw.get("category") or {}).get("name", ""),
                        "_source": "mfe_json",
                    })
                if items:
                    return items
        except Exception:
            pass

    # Fallback: regex on raw HTML (works for listing but loses some fields)
    for m in re.finditer(
        r'"id":(\d{10,12}),"categoryId":\d+.*?"urlPath":"([^"?]+)[^"]*".*?"title":"((?:[^"\\]|\\.){3,80})".*?"sortTimeStamp":(\d{13})',
        html, re.DOTALL
    ):
        items.append({
            "id": m.group(1),
            "url": f"https://www.avito.ru{m.group(2)}",
            "title": m.group(3).replace("\\n", " "),
            "sort_timestamp_ms": int(m.group(4)),
            "sort_datetime": str(datetime.datetime.fromtimestamp(int(m.group(4)) / 1000)),
            "_source": "regex",
        })

    return items


def extract_item_card(html: str) -> dict:
    """
    Extract full vacancy card data from item page HTML.

    Key fields available anonymously:
      id, title, description (HTML), address, price, price_string,
      seller (avatar, verification), shop (id, name),
      phone (mask, publicPhone), sortFormatedDate, timestamps,
      vacancyParams, category, location, isActive, statusId
    """
    data = decode_hydration_data(html)
    if not data:
        return {}

    try:
        loader = data.get("loaderData", {})
        item_loader = loader.get("catalog-or-main-or-item", {})
        buyer_item = item_loader.get("buyerItem", {})
        item = buyer_item.get("item", {})
        if not item:
            return {}

        phone = item.get("phone", {}) or {}
        price = item.get("formattedPrice", {}) or {}
        seller = item.get("seller", {}) or {}
        shop = item.get("shop", {}) or {}
        location = item.get("location", {}) or {}

        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "description": item.get("description", ""),
            "description_html": item.get("descriptionHtml", ""),
            "address": item.get("address", ""),
            "price_value": item.get("price"),
            "price_string": price.get("formatedString", ""),
            "price_postfix": price.get("postfix", ""),
            "sort_formatted_date": item.get("sortFormatedDate"),
            "finish_time": item.get("finishTime"),
            "is_active": item.get("isActive"),
            "status_id": item.get("statusId"),
            "category_id": item.get("categoryId"),
            "location_id": item.get("locationId"),
            "location_name": location.get("name"),
            "location_slug": location.get("slug"),
            "phone_mask": phone.get("mask"),
            "phone_public": phone.get("publicPhone"),
            "phone_is_anonymous": phone.get("isAnonymousNumber"),
            "seller_avatar": seller.get("avatar"),
            "seller_verified": (seller.get("verification") or {}).get("anyBadge"),
            "seller_tenure_since": seller.get("tenureSince"),
            "seller_tenure_medal": seller.get("tenureMedal"),
            "shop_id": shop.get("id"),
            "shop_name": shop.get("name"),
            "is_shop": shop.get("isShop"),
            "url": f"https://www.avito.ru{item.get('url', '')}",
            "images_count": len(item.get("images") or []),
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# httpx-based fetcher (primary - works without Playwright)
# ---------------------------------------------------------------------------

def fetch_listing_httpx(
    url: str,
    proxy_url: Optional[str] = None,
    timeout: float = 25.0,
) -> tuple[list[dict], dict]:
    """Fetch listing page and extract items. Returns (items, meta)."""
    client_kwargs = {
        "headers": HEADERS,
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url)

    html = resp.text
    meta = {
        "status": resp.status_code,
        "html_len": len(html),
        "proxy_used": proxy_url is not None,
    }

    # Extract total count
    count_m = re.search(r'"count":(\d+),"totalCount"', html)
    if count_m:
        meta["total_count"] = int(count_m.group(1))

    items = extract_listing_items(html)
    return items, meta


def fetch_item_httpx(
    url: str,
    proxy_url: Optional[str] = None,
    timeout: float = 25.0,
) -> dict:
    """Fetch item card and extract fields."""
    client_kwargs = {
        "headers": {**HEADERS, "Referer": "https://www.avito.ru/all/vakansii"},
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url)

    return extract_item_card(resp.text)


# ---------------------------------------------------------------------------
# Playwright browser factory (for fallback / JS-challenge bypass)
# ---------------------------------------------------------------------------

def make_stealth_browser(
    pw,
    headless: bool = True,
    proxy: Optional[dict] = None,
):
    """
    Launch Chromium with stealth + real UA. Returns (browser, context).
    Stealth is applied to CONTEXT — proven pattern from hh/fl that defeats
    DDoS-Guard with headless=True.
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
        },
    )
    stealth.apply_stealth_sync(context)
    return browser, context


def fetch_listing_playwright(
    url: str,
    headless: bool = True,
    proxy: Optional[dict] = None,
    wait_s: int = 6,
) -> tuple[list[dict], dict]:
    """Fetch listing via Playwright (fallback if httpx blocked)."""
    xhr_requests = []

    with sync_playwright() as pw:
        browser, context = make_stealth_browser(pw, headless=headless, proxy=proxy)
        page = context.new_page()

        def on_request(req):
            if req.resource_type in ("xhr", "fetch"):
                xhr_requests.append({"url": req.url, "method": req.method})

        page.on("request", on_request)
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        time.sleep(wait_s)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        html = page.content()
        ss_path = SAMPLES_DIR / "avito_playwright_listing.png"
        try:
            page.screenshot(path=str(ss_path))
        except Exception:
            pass

        page.close()
        browser.close()

    meta = {
        "html_len": len(html),
        "xhr_endpoints": [r["url"] for r in xhr_requests[:20]],
        "screenshot": str(ss_path),
    }
    items = extract_listing_items(html)
    return items, meta


# ---------------------------------------------------------------------------
# Standalone verification runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, random

    parser = argparse.ArgumentParser(description="avito.ru vacancies parser")
    parser.add_argument("--url", default="https://www.avito.ru/all/vakansii?s=104")
    parser.add_argument("--mode", default="httpx", choices=["httpx", "playwright"],
                        help="httpx (fast, no browser) or playwright (stealth browser)")
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    parser.add_argument("--proxy-port", default=None, help="Proxy port 11000-11099")
    parser.add_argument("--item-card", action="store_true", help="Also fetch first item card")
    args = parser.parse_args()

    headless = args.headless == "true"

    # Build proxy config
    proxy_playwright = None
    proxy_httpx = None
    if args.proxy_port:
        proxy_playwright = {
            "server": f"http://np.puls-proxy.com:{args.proxy_port}",
            "username": "efea0cd216087051c2e6__cr.ru;sessttl.10",
            "password": "fc6a3125b4c606fa",
        }
        enc_user = urllib.parse.quote("efea0cd216087051c2e6__cr.ru;sessttl.10", safe="")
        enc_pass = "fc6a3125b4c606fa"
        proxy_httpx = f"http://{enc_user}:{enc_pass}@np.puls-proxy.com:{args.proxy_port}"
    else:
        # Try random proxy from file
        proxy_urls = load_proxy_urls()
        proxy_plist = load_proxy_list()
        if proxy_urls:
            random.shuffle(proxy_urls)
            # We'll try direct first

    print(f"URL: {args.url}")
    print(f"Mode: {args.mode}")
    print(f"Proxy: {proxy_playwright or proxy_httpx or 'direct'}")

    if args.mode == "httpx":
        print("\n=== httpx fetch ===")
        try:
            items, meta = fetch_listing_httpx(args.url, proxy_url=proxy_httpx)
            print(f"Status: {meta.get('status')} | HTML: {meta.get('html_len')} chars | total: {meta.get('total_count')}")
            print(f"Items extracted: {len(items)}")
            for item in items[:5]:
                print(f"  [{item['id']}] {item['title'][:60]} | {item.get('price_string', '')} | {item.get('sort_datetime', '')}")

            # Save evidence
            evidence = {
                "url": args.url,
                "meta": meta,
                "items_count": len(items),
                "items_sample": items[:10],
                "anti_bot_verdict": "REAL_CONTENT" if items else "BLOCKED",
                "proxy_required": False,
            }
            ev_path = SAMPLES_DIR / "avito_playwright_evidence.json"
            ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nEvidence: {ev_path}")

            # Item card
            if args.item_card and items:
                print(f"\n=== Item card: {items[0]['url']} ===")
                card = fetch_item_httpx(items[0]["url"], proxy_url=proxy_httpx)
                print(f"  title: {card.get('title')}")
                print(f"  price: {card.get('price_string')} {card.get('price_postfix')}")
                print(f"  address: {card.get('address')}")
                print(f"  phone_mask: {card.get('phone_mask')}")
                print(f"  phone_public: {card.get('phone_public')}")
                print(f"  shop_id: {card.get('shop_id')} shop_name: {card.get('shop_name')}")
                print(f"  is_active: {card.get('is_active')}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback; traceback.print_exc()

    elif args.mode == "playwright":
        print("\n=== Playwright fetch ===")
        proxy_list = load_proxy_list()
        random.shuffle(proxy_list)
        proxy = proxy_playwright or (proxy_list[0] if proxy_list else None)

        items, meta = fetch_listing_playwright(args.url, headless=headless, proxy=proxy)
        print(f"HTML: {meta.get('html_len')} chars")
        print(f"Items: {len(items)}")
        for item in items[:5]:
            print(f"  [{item['id']}] {item['title'][:60]} | {item.get('sort_datetime', '')}")
        if meta.get("xhr_endpoints"):
            print(f"\nXHR endpoints:")
            for ep in meta["xhr_endpoints"][:10]:
                print(f"  {ep}")
