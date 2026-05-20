"""Approach 2 — official Places HTTP API (Geosearch).

  https://search-maps.yandex.ru/v1/?apikey=<KEY>&text=...&type=biz&lang=ru_RU

Without an apikey (and there is no public/free key), we expect either 401/403
or an error payload. The point of this test is to **document the refusal mode**
and to verify (a) the endpoint is reachable from our proxy IP and (b) the
official error matches what the docs claim. A working key would unlock the
documented response with `id`, `name`, `address`, `Categories`, `Phones`,
`Hours`, `geometry`, etc.
"""
from __future__ import annotations

import json
import time
import urllib3

import requests

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import requests_proxies, ExperimentResult, log_line, utf8_stdout, TARGET_QUERY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NAME = "02_official_geosearch"


def call(proxies, apikey: str | None):
    url = "https://search-maps.yandex.ru/v1/"
    params = {
        "text": f"{TARGET_QUERY} Санкт-Петербург",
        "type": "biz",
        "lang": "ru_RU",
        "results": 10,
        "ll": "30.315,59.939",
        "spn": "0.5,0.3",
    }
    if apikey:
        params["apikey"] = apikey
    for i in range(3):
        try:
            r = requests.get(url, params=params, proxies=proxies, timeout=30, verify=False,
                             headers={"Accept": "application/json"})
            return r
        except Exception as e:
            log_line(NAME, f"hiccup {i+1}: {str(e)[:120]}")
            time.sleep(2 * (i + 1))
    return None


def main() -> int:
    utf8_stdout()
    proxies = requests_proxies()
    res = ExperimentResult(approach="official Geosearch /v1/ (no API key)")
    t0 = time.perf_counter()

    # 1) no key
    r1 = call(proxies, None)
    if r1 is None:
        res.error = "proxy gave up on all retries"
    else:
        res.http_status = r1.status_code
        snippet = r1.text[:400].replace("\n", " ")
        log_line(NAME, f"no-key -> {r1.status_code} ({len(r1.content)}B) snippet={snippet!r}")
        res.notes = f"no-key: HTTP {r1.status_code}, body={snippet[:200]!r}"

    # 2) obviously invalid key — to differentiate "missing key" vs "invalid key"
    r2 = call(proxies, "00000000-0000-0000-0000-000000000000")
    if r2 is not None:
        snippet = r2.text[:400].replace("\n", " ")
        log_line(NAME, f"fake-key -> {r2.status_code} snippet={snippet!r}")
        res.notes += f" | fake-key: HTTP {r2.status_code}"
        res.sample = [{"no_key_status": getattr(r1, "status_code", None),
                       "no_key_body": (r1.text if r1 else "")[:600],
                       "fake_key_status": r2.status_code,
                       "fake_key_body": r2.text[:600]}]

    res.success = False  # by definition cannot succeed without a real key
    res.duration_s = round(time.perf_counter() - t0, 2)
    res.save(NAME)
    log_line(NAME, "verdict: requires paid annual contract; not usable for a local self-hosted directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
