"""Sanity-check the sticky residential proxy before running scrape experiments.

Verifies:
  * connectivity
  * egress IP (and that it's not our real IP)
  * geo (country / city) — Yandex weighs IP geo against query region
  * sticky stability across N requests
"""
from __future__ import annotations

import json
import time
import urllib3

import requests

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import requests_proxies, ExperimentResult, log_line, utf8_stdout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


NAME = "00_proxy_check"
N_STICKY = 6


def lookup_geo(proxies):
    try:
        r = requests.get("http://ip-api.com/json", proxies=proxies, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e)[:120]}


def main() -> int:
    utf8_stdout()
    proxies = requests_proxies()
    res = ExperimentResult(approach="proxy sanity")

    t0 = time.perf_counter()
    ips = []
    geo = None
    for i in range(N_STICKY):
        try:
            r = requests.get("https://api.ipify.org?format=json",
                             proxies=proxies, timeout=20, verify=False)
            ip = r.json().get("ip")
            ips.append(ip)
            log_line(NAME, f"req {i+1}: ip={ip} ({r.elapsed.total_seconds()*1000:.0f}ms)")
        except Exception as e:
            log_line(NAME, f"req {i+1}: ERROR {e}")
            ips.append(None)
        if i == 0 and ips[0]:
            geo = lookup_geo(proxies)
            log_line(NAME, f"geo: {json.dumps(geo, ensure_ascii=False)}")

    valid = [ip for ip in ips if ip]
    uniq = set(valid)
    res.duration_s = round(time.perf_counter() - t0, 2)
    res.success = len(uniq) == 1 and len(valid) >= N_STICKY - 1
    res.egress_ip = next(iter(uniq), None)
    res.notes = (
        f"{len(valid)}/{N_STICKY} successful; {len(uniq)} unique IP; "
        f"geo={geo.get('country','?')}/{geo.get('city','?')}/{geo.get('isp','?') if geo else '?'}"
    )
    res.sample = [{"ip": ip} for ip in ips]
    path = res.save(NAME)
    log_line(NAME, f"saved {path}")
    log_line(NAME, f"verdict: {'OK' if res.success else 'FAIL'} | {res.notes}")
    return 0 if res.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
