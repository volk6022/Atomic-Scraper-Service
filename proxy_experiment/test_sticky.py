#!/usr/bin/env python3
"""
Sticky proxy tester for puls-proxy.com (sessttl.30 — IP fixed for 30 min).
Key checks:
  1. Proxy connects and routes traffic
  2. ALL requests return the SAME IP (sticky session is working)
  3. Data integrity over multiple requests
  4. Headers look clean (no proxy leaks)
"""

import time
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "requests[socks]"], check=True)
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HTTP_PROXY = "http://efea0cd216087051c2e6__cr.ru;sessttl.30:fc6a3125b4c606fa@np.puls-proxy.com:11000"
PROXIES    = {"http": HTTP_PROXY, "https": HTTP_PROXY}
TIMEOUT    = 25

SITES = [
    ("httpbin /ip",     "https://httpbin.org/ip"),
    ("ipinfo.io",       "https://ipinfo.io/json"),
    ("ip-api.com",      "http://ip-api.com/json"),
    ("api.ipify.org",   "https://api.ipify.org?format=json"),
    ("httpbin /get",    "https://httpbin.org/get"),
    ("example.com",     "https://example.com"),
    ("httpbin /html",   "https://httpbin.org/html"),
    ("httpbin /bytes",  "https://httpbin.org/bytes/8192"),
]


def get_ip(url: str, text: str) -> str | None:
    try:
        d = json.loads(text)
        return d.get("origin") or d.get("ip") or d.get("query")
    except Exception:
        s = text.strip()
        return s if s else None


def hit(url: str, label: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.get(url, proxies=PROXIES, timeout=TIMEOUT, verify=False)
        ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        ip = get_ip(url, r.text)
        return dict(ok=True, label=label, ms=ms, ip=ip, size=len(r.content),
                    status=r.status_code, headers=dict(r.headers), error=None)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return dict(ok=False, label=label, ms=ms, ip=None, size=0,
                    status=None, headers={}, error=str(e)[:120])


def section(t: str):
    print(f"\n{'─'*64}\n  {t}\n{'─'*64}")


def main():
    print("=" * 64)
    print("  PULS STICKY PROXY TESTER  (sessttl.30 — same IP for 30 min)")
    print("=" * 64)
    print(f"  Proxy: {HTTP_PROXY}")

    # ── 0. Real IP ──────────────────────────────────────────────────────────
    section("0. Real IP (no proxy)")
    try:
        real_ip = requests.get("https://httpbin.org/ip", timeout=10).json()["origin"]
        print(f"  Real IP: {real_ip}")
    except Exception as e:
        real_ip = None
        print(f"  Could not fetch: {e}")

    # ── 1. Site sweep ────────────────────────────────────────────────────────
    section("1. Site sweep")
    results = []
    for label, url in SITES:
        r = hit(url, label)
        results.append(r)
        mark = "✓" if r["ok"] else "✗"
        size = f"{r['size']:,}B" if r["ok"] else ""
        ip   = r["ip"] or ""
        err  = f"  <- {r['error']}" if r["error"] else ""
        print(f"  {mark} {label:<20} {r['ms']:>7.0f}ms  {size:<10} {ip}{err}")

    # ── 2. Sticky check — 10 requests, all must share one IP ─────────────────
    N = 10
    section(f"2. Sticky session check — {N} requests, expect ONE shared IP")
    ips = []
    for i in range(N):
        r = hit("https://httpbin.org/ip", f"req {i+1}")
        ip = r["ip"]
        ips.append(ip)
        mark = "✓" if r["ok"] else "✗"
        diff = ""
        if ip and ips[:-1]:
            prev = [x for x in ips[:-1] if x]
            if prev and ip != prev[-1]:
                diff = "  *** IP CHANGED ***"
        print(f"  {mark} req {i+1:>2}: {ip or r['error']:<20} ({r['ms']:.0f}ms){diff}")

    valid_ips  = [ip for ip in ips if ip]
    unique_ips = set(valid_ips)

    print(f"\n  Unique IPs seen: {len(unique_ips)}")
    for ip in unique_ips:
        print(f"    {ip}")

    if len(unique_ips) == 1:
        print("  ✓ Sticky session confirmed — IP is stable")
    elif len(unique_ips) == 0:
        print("  ✗ No successful responses — proxy may be down")
    else:
        print(f"  ! IP changed {len(unique_ips)-1} time(s) — session not fully sticky")

    # ── 3. Header inspection — check for proxy leakage ───────────────────────
    section("3. Response header inspection (proxy leak check)")
    r = hit("https://httpbin.org/get", "header check")
    if r["ok"]:
        try:
            data = requests.get("https://httpbin.org/get", proxies=PROXIES,
                                timeout=TIMEOUT, verify=False).json()
            req_headers = data.get("headers", {})
            suspicious = {k: v for k, v in req_headers.items()
                          if any(x in k.lower() for x in
                                 ["proxy", "forwarded", "via", "x-real", "x-forward"])}
            if suspicious:
                print("  ! Proxy-revealing headers found in request:")
                for k, v in suspicious.items():
                    print(f"      {k}: {v}")
            else:
                print("  ✓ No proxy-revealing headers in request")

            print(f"  User-Agent seen by server: {req_headers.get('User-Agent', 'n/a')}")
            print(f"  Origin IP seen by server:  {data.get('origin')}")
        except Exception as e:
            print(f"  Could not parse: {e}")
    else:
        print(f"  Could not connect: {r['error']}")

    # ── Summary ───────────────────────────────────────────────────────────────
    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{'='*64}")
    print("  SUMMARY")
    print(f"{'='*64}")
    print(f"  Sites reachable:   {ok_count}/{len(SITES)}")
    print(f"  Sticky IP stable:  {'YES' if len(unique_ips) == 1 else 'NO (' + str(len(unique_ips)) + ' unique IPs)'}")
    if real_ip and real_ip in valid_ips:
        print("  IP leak:           !! REAL IP EXPOSED !!")
    else:
        print("  IP leak:           none")

    sticky_ok = ok_count >= len(SITES) * 0.7 and len(unique_ips) == 1
    print(f"\n  Verdict: {'✓ Sticky proxy is WORKING — safe to use with Google' if sticky_ok else '✗ Issues detected — review above'}")
    print()


if __name__ == "__main__":
    main()
