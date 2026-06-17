"""Approach 1b — fetch the SPB search HTML and extract org list from inline JSON.

Yandex Maps is a SPA; the first server-rendered HTML embeds the initial list of
business snippets inside <script> tags. If we can locate that JSON we get the
data without ever hitting the protected /maps/api/search endpoint.
"""
from __future__ import annotations

import json
import re
import time
import urllib3

import requests
from bs4 import BeautifulSoup

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (
    requests_proxies, ExperimentResult, log_line, utf8_stdout,
    TARGET_QUERY, SPB_REGION_ID, RESULTS_DIR,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NAME = "01b_bootstrap_html_parse"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def fetch_html(proxies, attempts=4):
    url = f"https://yandex.ru/maps/{SPB_REGION_ID}/saint-petersburg/search/{requests.utils.quote(TARGET_QUERY)}/"
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers=headers, proxies=proxies, timeout=30, verify=False)
            return r
        except Exception as e:
            last = e
            log_line(NAME, f"hiccup {i+1}: {str(e)[:120]}")
            time.sleep(2 * (i + 1))
    raise last


def harvest_jsons_from_html(html: str):
    """Find all JSON-looking script blocks and return parsed candidates."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for sc in soup.find_all("script"):
        txt = (sc.string or sc.get_text() or "").strip()
        if not txt or len(txt) < 200:
            continue
        # Common patterns Yandex uses
        candidates = []
        # 1) window.__bootstrap__ = {...};
        m = re.search(r"window\.__([A-Za-z_]+)__\s*=\s*(\{.*?\});", txt, re.S)
        if m:
            candidates.append(("window." + m.group(1), m.group(2)))
        # 2) JSON.parse('...')
        for jp in re.finditer(r"JSON\.parse\(\s*'(.+?)'\s*\)", txt, re.S):
            candidates.append(("JSON.parse", jp.group(1).encode().decode("unicode_escape")))
        # 3) raw json blob (rare)
        if not candidates and txt.startswith("{") and txt.endswith("}"):
            candidates.append(("raw_json", txt))
        for label, raw in candidates:
            try:
                blocks.append((label, json.loads(raw)))
            except Exception:
                pass
    return blocks


def find_business_items(obj, found=None, depth=0):
    """Walk JSON looking for objects that look like business snippets."""
    if found is None:
        found = []
    if depth > 12 or len(found) > 200:
        return found
    if isinstance(obj, dict):
        keys = set(obj.keys())
        # Yandex business snippets typically have these keys
        signals = {"businessId", "business_id", "oid", "encoded_id"}
        has_name = ("name" in obj) or ("title" in obj)
        has_coord = ("coordinates" in obj) or ("point" in obj) or ("geometry" in obj)
        has_addr = ("address" in obj) or ("fullAddress" in obj) or ("addressTranslit" in obj)
        if (signals & keys) and has_name and (has_coord or has_addr):
            found.append(obj)
        for v in obj.values():
            find_business_items(v, found, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            find_business_items(v, found, depth + 1)
    return found


def main() -> int:
    utf8_stdout()
    proxies = requests_proxies()
    res = ExperimentResult(approach="HTML bootstrap parse")
    t0 = time.perf_counter()

    r = fetch_html(proxies)
    res.http_status = r.status_code
    log_line(NAME, f"GET {r.url} -> {r.status_code} ({len(r.content)}B)")

    html = r.text
    if "showcaptcha" in html.lower() or "smartcaptcha" in html.lower():
        res.captcha_detected = True
        res.notes = "captcha returned"
    else:
        (RESULTS_DIR / f"{NAME}_raw.html").write_text(html, encoding="utf-8")
        blocks = harvest_jsons_from_html(html)
        log_line(NAME, f"parsed JSON blocks: {len(blocks)} ({[b[0] for b in blocks][:5]})")

        items = []
        for label, blob in blocks:
            found = find_business_items(blob)
            if found:
                log_line(NAME, f"-> {label} yielded {len(found)} business items")
                items.extend(found)
                break

        # Fallback regex: look for "businessId":"..." patterns
        if not items:
            oids = sorted(set(re.findall(r'"businessId"\s*:\s*"?(\d{6,})"?', html)))
            log_line(NAME, f"regex fallback found businessIds: {len(oids)} (sample={oids[:5]})")
            if oids:
                items = [{"businessId": oid} for oid in oids]
                res.notes += " (only IDs via regex; need a separate fetch for full fields)"

        res.items_collected = len(items)
        res.success = res.items_collected > 0
        if items:
            first = items[0]
            if isinstance(first, dict):
                res.fields_per_item = sorted(first.keys())[:30]
                # trim to avoid mega-blobs
                res.sample = [
                    {k: (v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)[:200])
                     for k, v in (it if isinstance(it, dict) else {}).items()}
                    for it in items[:3]
                ]

    res.duration_s = round(time.perf_counter() - t0, 2)
    path = res.save(NAME)
    log_line(NAME, f"saved {path}")
    log_line(NAME, f"verdict: success={res.success} items={res.items_collected} captcha={res.captcha_detected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
