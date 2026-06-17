# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Comprehensive proxy tester for puls-proxy.com
Tests HTTP and SOCKS5 proxies: connectivity, data transfer, IP rotation.

Country selection: replace '__cr.ru' in username with '__cr.XX' where XX is country code.
Examples: .ru (Russia), .in (India), .de (Germany), .us (United States), .gb (UK)
"""

import time
import json
import sys
import io
import re

# Force UTF-8 output so Unicode symbols work on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("[!] Installing requests[socks]...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "requests[socks]"], check=True)
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── Proxy config ─────────────────────────────────────────────────────────────
HTTP_PROXY  = "http://efea0cd216087051c2e6__cr.ru:fc6a3125b4c606fa@np.puls-proxy.com:823"
SOCKS5_PROXY = "socks5://efea0cd216087051c2e6__cr.ru:fc6a3125b4c606fa@np.puls-proxy.com:824"

HTTP_PROXIES   = {"http": HTTP_PROXY,   "https": HTTP_PROXY}
SOCKS5_PROXIES = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}

# ─── Test targets ─────────────────────────────────────────────────────────────
SITES = [
    ("httpbin /ip",         "https://httpbin.org/ip"),
    ("httpbin /get",        "https://httpbin.org/get"),
    ("ipinfo.io",           "https://ipinfo.io/json"),
    ("api.ipify.org",       "https://api.ipify.org?format=json"),
    ("icanhazip.com",       "https://icanhazip.com"),
    ("ifconfig.me",         "https://ifconfig.me/ip"),
    ("ip-api.com",          "http://ip-api.com/json"),           # http only intentionally
    ("example.com",         "https://example.com"),              # real HTML page
    ("httpbin /html",       "https://httpbin.org/html"),
    ("httpbin /bytes/4096", "https://httpbin.org/bytes/4096"),   # binary data
]

TIMEOUT = 20

# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_ip(url: str, text: str) -> tuple[str | None, str | None]:
    ip, country = None, None
    try:
        data = json.loads(text)
        if "origin" in data:
            ip = data["origin"]
        elif "ip" in data:
            ip = data["ip"]
            country = data.get("country") or data.get("countryCode")
        elif "query" in data:
            ip = data["query"]
            country = data.get("country")
    except Exception:
        candidate = text.strip().split()[0] if text.strip() else ""
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", candidate):
            ip = candidate
    return ip, country


def hit(proxies: dict, url: str, label: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.get(url, proxies=proxies, timeout=TIMEOUT, verify=False)
        elapsed = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        ip, country = extract_ip(url, r.text)
        size = len(r.content)
        return dict(ok=True, label=label, ms=elapsed, ip=ip, country=country,
                    status=r.status_code, size=size, error=None)
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return dict(ok=False, label=label, ms=elapsed, ip=None, country=None,
                    status=None, size=0, error=str(e)[:120])


def print_row(r: dict):
    mark = "✓" if r["ok"] else "✗"
    ip_info = r["ip"] or ""
    if r["country"]:
        ip_info += f" ({r['country']})"
    size_info = f"{r['size']:,}B" if r["ok"] else ""
    err_info  = f"  ← {r['error']}" if r["error"] else ""
    print(f"  {mark} {r['label']:<22} {r['ms']:>7.0f}ms  {size_info:<10} {ip_info}{err_info}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def section(title: str):
    print(f"\n{'─'*64}")
    print(f"  {title}")
    print(f"{'─'*64}")


def main():
    print("=" * 64)
    print("  PULS PROXY TESTER")
    print("=" * 64)
    print(f"  HTTP   → {HTTP_PROXY}")
    print(f"  SOCKS5 → {SOCKS5_PROXY}")

    # ── 0. Real IP baseline ──────────────────────────────────────────────────
    section("0. Your real IP (no proxy)")
    try:
        r = requests.get("https://httpbin.org/ip", timeout=10)
        real_ip = r.json().get("origin")
        print(f"  Real IP: {real_ip}")
    except Exception as e:
        real_ip = None
        print(f"  Could not fetch: {e}")

    # ── 1. HTTP proxy: all sites ─────────────────────────────────────────────
    section("1. HTTP proxy — site sweep")
    http_results = []
    for label, url in SITES:
        res = hit(HTTP_PROXIES, url, label)
        http_results.append(res)
        print_row(res)

    # ── 2. SOCKS5 proxy: all sites ───────────────────────────────────────────
    section("2. SOCKS5 proxy — site sweep")
    socks5_results = []
    for label, url in SITES:
        res = hit(SOCKS5_PROXIES, url, label)
        socks5_results.append(res)
        print_row(res)

    # ── 3. IP rotation check ─────────────────────────────────────────────────
    N_ROTATION = 7
    section(f"3. IP rotation — HTTP proxy ({N_ROTATION} sequential requests)")
    http_ips = []
    for i in range(N_ROTATION):
        res = hit(HTTP_PROXIES, "https://httpbin.org/ip", f"req #{i+1}")
        ip = res["ip"]
        http_ips.append(ip)
        mark = "✓" if res["ok"] else "✗"
        same = " ← SAME" if ip and http_ips[:-1] and ip == http_ips[-2] else ""
        print(f"  {mark} req {i+1}: {ip or res['error']}{same}  ({res['ms']:.0f}ms)")

    section(f"4. IP rotation — SOCKS5 proxy ({N_ROTATION} sequential requests)")
    socks5_ips = []
    for i in range(N_ROTATION):
        res = hit(SOCKS5_PROXIES, "https://httpbin.org/ip", f"req #{i+1}")
        ip = res["ip"]
        socks5_ips.append(ip)
        mark = "✓" if res["ok"] else "✗"
        same = " ← SAME" if ip and socks5_ips[:-1] and ip == socks5_ips[-2] else ""
        print(f"  {mark} req {i+1}: {ip or res['error']}{same}  ({res['ms']:.0f}ms)")

    # ── 5. Data integrity check ───────────────────────────────────────────────
    section("5. Data integrity — compare direct vs proxy response")
    check_url = "https://httpbin.org/get"
    try:
        direct = requests.get(check_url, timeout=15, verify=False).json()
        via_http = requests.get(check_url, proxies=HTTP_PROXIES, timeout=TIMEOUT, verify=False).json()
        via_socks = requests.get(check_url, proxies=SOCKS5_PROXIES, timeout=TIMEOUT, verify=False).json()

        keys_ok_http  = set(direct.keys()) == set(via_http.keys())
        keys_ok_socks = set(direct.keys()) == set(via_socks.keys())
        print(f"  {'✓' if keys_ok_http  else '✗'} HTTP   response structure matches direct")
        print(f"  {'✓' if keys_ok_socks else '✗'} SOCKS5 response structure matches direct")
        print(f"  Direct headers count:  {len(direct.get('headers', {}))}")
        print(f"  HTTP   headers count:  {len(via_http.get('headers', {}))}")
        print(f"  SOCKS5 headers count:  {len(via_socks.get('headers', {}))}")
    except Exception as e:
        print(f"  Could not complete integrity check: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  SUMMARY")
    print(f"{'='*64}")

    http_ok   = sum(1 for r in http_results   if r["ok"])
    socks5_ok = sum(1 for r in socks5_results if r["ok"])
    n = len(SITES)

    valid_http_ips   = [ip for ip in http_ips   if ip and not ip.startswith("ERROR")]
    valid_socks5_ips = [ip for ip in socks5_ips if ip and not ip.startswith("ERROR")]
    unique_http   = len(set(valid_http_ips))
    unique_socks5 = len(set(valid_socks5_ips))

    print(f"  HTTP   proxy: {http_ok}/{n} sites OK")
    print(f"  SOCKS5 proxy: {socks5_ok}/{n} sites OK")
    print(f"  HTTP   rotation: {unique_http} unique IPs / {N_ROTATION} requests")
    print(f"  SOCKS5 rotation: {unique_socks5} unique IPs / {N_ROTATION} requests")

    if real_ip:
        proxy_ips = set(valid_http_ips + valid_socks5_ips)
        leaked = real_ip in proxy_ips
        print(f"  IP leak check: {'⚠ REAL IP SEEN IN PROXY RESPONSES' if leaked else '✓ real IP not exposed'}")

    print()
    if http_ok > 0 and socks5_ok > 0:
        print("  ✓ Both proxy types are WORKING")
    elif http_ok > 0:
        print("  ~ HTTP proxy works; SOCKS5 has issues")
    elif socks5_ok > 0:
        print("  ~ SOCKS5 proxy works; HTTP has issues")
    else:
        print("  ✗ Proxies appear DOWN or misconfigured")


if __name__ == "__main__":
    main()
