"""Approach 1 — direct HTTP to the public web app's internal search endpoint.

Per docs/yandex-maps-scraping.md §3:
  https://yandex.ru/maps/api/search?text=<q>&...

The web app calls this with a session token, not an apikey. We try a few realistic
shapes (with/without csrfToken, with/without session cookie obtained from a HEAD
on the main page). Goal: see what bare cURL-like calls return through our RU
residential proxy (per doc, "the simple cURL approach often returns 'Загрузка…'
placeholders" and triggers SmartCaptcha quickly).
"""
from __future__ import annotations

import json
import re
import time
import urllib3
import warnings

import requests

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (
    requests_proxies, ExperimentResult, log_line, utf8_stdout,
    TARGET_QUERY, SPB_REGION_ID,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

NAME = "01_direct_http_public_search"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://yandex.ru/maps/",
    "Origin": "https://yandex.ru",
}


def is_captcha(text: str) -> bool:
    t = text.lower()
    return (
        "smartcaptcha" in t
        or "showcaptcha" in t
        or "checkboxcaptcha-anchor" in t
        or 'class="captcha"' in t
        or "хм, а вы человек" in t
        or "are you human" in t
        or "yandex.com/showcaptcha" in t
    )


def _get_with_retry(s, url, *, timeout=30, allow_redirects=True, params=None, headers=None, attempts=4):
    last = None
    for i in range(attempts):
        try:
            return s.get(url, timeout=timeout, allow_redirects=allow_redirects,
                         params=params, headers=headers)
        except requests.exceptions.ProxyError as e:
            last = e
            log_line(NAME, f"proxy hiccup (try {i+1}/{attempts}) on {url}: {str(e)[:120]}")
            time.sleep(2 * (i + 1))
        except requests.exceptions.RequestException as e:
            last = e
            log_line(NAME, f"req error (try {i+1}/{attempts}) on {url}: {str(e)[:120]}")
            time.sleep(2 * (i + 1))
    raise last


def warm_cookies(proxies):
    """Hit the SPB search page to seed cookies before calling the JSON API."""
    s = requests.Session()
    s.proxies = proxies
    s.verify = False
    s.headers.update({"User-Agent": UA,
                      "Accept-Language": "ru-RU,ru;q=0.9",
                      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    url = f"https://yandex.ru/maps/{SPB_REGION_ID}/saint-petersburg/search/{requests.utils.quote(TARGET_QUERY)}/"
    r = _get_with_retry(s, url)
    cookie_names = sorted(s.cookies.get_dict().keys())
    log_line(NAME, f"warmup GET {url} -> {r.status_code} ({len(r.content)}B) cookies={cookie_names}")
    return s, r


def try_internal_api(s, proxies, csrf: str | None = None):
    """Best-effort call to yandex.ru/maps/api/search.

    Yandex returns {"csrfToken": "..."} on first call without a valid token —
    pass that token back as csrfToken= to get the real payload.
    """
    url = "https://yandex.ru/maps/api/search"
    params = {
        "text": TARGET_QUERY,
        "ll": "30.315,59.939",
        "spn": "0.5,0.3",
        "z": 11,
        "lang": "ru_RU",
        "lr": SPB_REGION_ID,
        "ajax": 1,
        "results": 24,
    }
    if csrf:
        params["csrfToken"] = csrf
    headers = dict(BASE_HEADERS)
    try:
        r = _get_with_retry(s, url, params=params, headers=headers, timeout=30)
        snippet = r.text[:300]
        log_line(NAME, f"GET {r.url} -> {r.status_code} ({len(r.content)}B) snippet={snippet!r}")
        return r
    except Exception as e:
        log_line(NAME, f"GET /maps/api/search failed: {e}")
        return None


def main() -> int:
    utf8_stdout()
    proxies = requests_proxies()
    res = ExperimentResult(approach="direct HTTP -> yandex.ru/maps/api/search")
    t0 = time.perf_counter()

    s, warm = warm_cookies(proxies)
    captcha = is_captcha(warm.text)
    res.captcha_detected = captcha
    res.http_status = warm.status_code
    if captcha:
        res.notes = "Warmup page already returns SmartCaptcha challenge HTML."
    else:
        res.notes = "Warmup OK; trying internal /maps/api/search."

    # First call — usually returns just {"csrfToken": "..."}
    r = try_internal_api(s, proxies)
    csrf = None
    if r is not None and r.status_code == 200:
        try:
            j = r.json()
            csrf = j.get("csrfToken")
            log_line(NAME, f"first /maps/api/search payload keys: {sorted(j.keys())}; csrf={'yes' if csrf else 'no'}")
        except Exception:
            pass

    # Retry with csrf if we got one
    if csrf:
        time.sleep(1.0)
        r = try_internal_api(s, proxies, csrf=csrf)

    if r is None:
        res.error = "exception during /maps/api/search"
        res.success = False
    else:
        res.http_status = r.status_code
        if is_captcha(r.text):
            res.captcha_detected = True
            res.notes += " | API call returned captcha HTML."
        try:
            data = r.json()
            log_line(NAME, f"final payload top-level keys: {sorted(data.keys())[:15]}")
            # Possible item containers
            items = []
            for path in (
                ("data", "items"), ("data", "search_results"), ("items",),
                ("data", "features"), ("features",),
            ):
                cur = data
                ok = True
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, list) and cur:
                    items = cur
                    log_line(NAME, f"items found under {'.'.join(path)} (count={len(cur)})")
                    break
            res.items_collected = len(items)
            res.success = res.items_collected > 0
            if items:
                first = items[0]
                if isinstance(first, dict):
                    res.fields_per_item = sorted(first.keys())
                    res.sample = items[:3]
            else:
                res.sample = [{"top_level_snippet": json.dumps(data, ensure_ascii=False)[:800]}]
        except Exception as e:
            res.notes += f" | JSON parse failed: {e}"
            res.sample = [{"raw_snippet": r.text[:400]}]

    res.duration_s = round(time.perf_counter() - t0, 2)
    path = res.save(NAME)
    log_line(NAME, f"saved {path}")
    log_line(NAME, f"verdict: success={res.success} captcha={res.captcha_detected} items={res.items_collected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
