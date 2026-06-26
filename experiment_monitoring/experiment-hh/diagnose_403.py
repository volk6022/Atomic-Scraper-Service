"""
diagnose_403.py — figure out why api.hh.ru returns 403.

Tests:
1. Direct request (no proxy) — does the API work without proxy?
2. With proxy + different User-Agent (HH official UA example)
3. With proxy + HH-User-Agent header
4. Check /openapi/specification/public (different endpoint)
5. Test api.hh.ru root endpoint
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import load_proxies, _encode_proxy_url, _LINE_RE, PROXIES_FILE

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


def req(label: str, url: str, proxy_url: str | None = None, headers: dict | None = None, params: dict | None = None) -> None:
    h = {
        "Accept": "application/json",
        **(headers or {}),
    }
    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=25.0,
            headers=h,
            follow_redirects=True,
        ) as client:
            resp = client.get(url, params=params)
        print(f"\n[{label}]")
        print(f"  URL: {url}")
        print(f"  Proxy: {proxy_url.split('@')[-1] if proxy_url else 'NONE (direct)'}")
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('content-type', '?')}")
        if resp.status_code != 200:
            print(f"  Body (first 400): {resp.text[:400]}")
        else:
            body = resp.text[:200]
            print(f"  Body (first 200): {body}")
        # Save all-headers for inspection
        print(f"  Response headers: {dict(resp.headers)}")
        return resp.status_code
    except Exception as exc:
        print(f"\n[{label}]  ERROR: {type(exc).__name__}: {exc}")
        return None


def pick_working_proxy() -> str | None:
    """Find first proxy that can reach api.hh.ru (even if 403)."""
    proxies = load_proxies()
    for p in proxies[:20]:
        try:
            with httpx.Client(proxy=p, timeout=15.0, follow_redirects=True) as c:
                r = c.get("https://api.hh.ru/")
            print(f"  proxy {p.split('@')[-1]} → HTTP {r.status_code}")
            if r.status_code < 500:
                return p
        except Exception as e:
            print(f"  proxy {p.split('@')[-1]} → FAIL: {type(e).__name__}")
    return None


def main():
    print("=== Diagnosing 403 on api.hh.ru ===\n")

    # 1. Direct request (no proxy)
    req("DIRECT no-proxy", "https://api.hh.ru/vacancies",
        proxy_url=None,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        params={"text": "python", "per_page": 5})

    # 2. Direct: api root
    req("DIRECT api root", "https://api.hh.ru/",
        proxy_url=None,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    # 3. Find a working proxy
    print("\nLooking for a working proxy...")
    proxy = pick_working_proxy()
    if proxy is None:
        print("No working proxy found in first 20. Trying more...")
        proxies = load_proxies()
        for p in proxies[20:40]:
            try:
                with httpx.Client(proxy=p, timeout=15.0, follow_redirects=True) as c:
                    r = c.get("https://api.hh.ru/")
                print(f"  proxy {p.split('@')[-1]} → HTTP {r.status_code}")
                if r.status_code < 500:
                    proxy = p
                    break
            except Exception as e:
                print(f"  proxy {p.split('@')[-1]} → FAIL: {type(e).__name__}")

    if proxy:
        print(f"\nUsing proxy: {proxy.split('@')[-1]}")

        # 4. Proxy + default minimal headers
        req("PROXY minimal UA", "https://api.hh.ru/vacancies",
            proxy_url=proxy,
            headers={"User-Agent": "my-app/1.0 (my@email.com)"},
            params={"text": "python", "per_page": 5})

        # 5. Proxy + browser UA
        req("PROXY browser UA", "https://api.hh.ru/vacancies",
            proxy_url=proxy,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
            params={"text": "python", "per_page": 5})

        # 6. Proxy + HH-User-Agent header (official format)
        req("PROXY HH-User-Agent header", "https://api.hh.ru/vacancies",
            proxy_url=proxy,
            headers={
                "User-Agent": "HHVerify/1.0 (vpncreatedakk@gmail.com)",
                "HH-User-Agent": "HHVerify/1.0 (vpncreatedakk@gmail.com)",
            },
            params={"text": "python", "per_page": 5})

        # 7. Proxy + api root
        req("PROXY api root", "https://api.hh.ru/",
            proxy_url=proxy)

        # 8. Proxy + dictionaries (lighter endpoint)
        req("PROXY /dictionaries", "https://api.hh.ru/dictionaries",
            proxy_url=proxy,
            headers={"User-Agent": "HHVerify/1.0 (vpncreatedakk@gmail.com)"})

        # 9. Proxy + areas (lighter)
        req("PROXY /areas", "https://api.hh.ru/areas",
            proxy_url=proxy,
            headers={"User-Agent": "HHVerify/1.0 (vpncreatedakk@gmail.com)"})

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
