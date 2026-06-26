"""
check_forbidden_type.py

The 403 body is: {"errors":[{"type":"forbidden"}], "request_id":"..."}
This does NOT match ErrorsCommonCaptchaErrors (which would have captcha_url).
This matches a plain "forbidden" error.

Key insight: HH API has been restricting anonymous access to /vacancies
from residential/RU IPs. The endpoint may require:
- A registered application token (even for read-only)
- Or has geo-blocking for certain IP ranges

Let's:
1. Check the GitHub docs for any recent changes to anonymous access policy
2. Check if there's a way to get a guest/anonymous token
3. Try the /vacancies endpoint with different params (no text, just area)
4. Test /vacancies/{id} for a known vacancy
5. Check if there's an app_id / client_id header approach
6. Try with Playwright stealth as fallback verification
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from proxy_client import load_proxies

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


def req_proxy(proxy: str, url: str, params: dict | None = None,
              headers: dict | None = None, timeout: float = 30.0) -> tuple[int, str]:
    h = {"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)",
         "Accept": "application/json", **(headers or {})}
    try:
        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=True, headers=h) as c:
            r = c.get(url, params=params or {})
            return r.status_code, r.text[:400]
    except Exception as e:
        return -1, str(e)[:200]


def main():
    proxies = load_proxies()

    # Find a working proxy
    proxy = None
    for p in proxies[:50]:
        try:
            with httpx.Client(proxy=p, timeout=10.0, follow_redirects=True,
                              headers={"User-Agent": "test/1.0"}) as c:
                r = c.get("https://api.hh.ru/dictionaries")
                if r.status_code == 200:
                    proxy = p
                    print(f"Working proxy: {p.split('@')[-1]}")
                    break
        except Exception:
            pass

    if not proxy:
        print("No working proxy found")
        return

    print("\n=== Test various /vacancies params ===")

    tests = [
        # No text filter - just area
        ("no text, just area=1", "https://api.hh.ru/vacancies", {"area": "1", "per_page": 5}),
        # With period instead of date_from
        ("period=1", "https://api.hh.ru/vacancies", {"text": "python", "period": "1", "per_page": 5}),
        # Minimal params
        ("minimal", "https://api.hh.ru/vacancies", {"per_page": 1}),
        # Different endpoint format
        ("no params", "https://api.hh.ru/vacancies", {}),
        # Try the v1 endpoint format
        ("v1 attempt", "https://api.hh.ru/v1/vacancies", {"text": "python", "per_page": 5}),
        # Try HH for employers (manager) endpoint
        ("employers list", "https://api.hh.ru/employers", {"text": "yandex", "per_page": 5}),
    ]

    for label, url, params in tests:
        status, body = req_proxy(proxy, url, params)
        print(f"  [{label}] {status}: {body[:200]}")

    print("\n=== Test if /vacancies/{id} works ===")
    # Known vacancy IDs from hh.ru (recent ML vacancies)
    for vid in ["102776520", "116855878", "118327254", "120000000"]:
        status, body = req_proxy(proxy, f"https://api.hh.ru/vacancies/{vid}", {})
        print(f"  /vacancies/{vid}: {status} — {body[:150]}")

    print("\n=== Test employer endpoints ===")
    for eid in ["1057", "15478", "906557"]:
        status, body = req_proxy(proxy, f"https://api.hh.ru/employers/{eid}", {})
        print(f"  /employers/{eid}: {status} — {body[:150]}")

    print("\n=== Check /vacancies with HH-User-Agent header ===")
    # Some apps send HH-User-Agent as a separate header
    for ua_style in [
        ("standard", {"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)"}),
        ("browser", {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}),
        ("no_ua", {}),
    ]:
        label, extra_h = ua_style
        status, body = req_proxy(
            proxy, "https://api.hh.ru/vacancies",
            {"text": "python", "per_page": 5},
            headers={**extra_h, "Accept": "application/json"}
        )
        print(f"  [{label}]: {status} — {body[:150]}")

    print("\n=== Check /openapi endpoint for current restrictions ===")
    # Try fetching the swagger UI or docs
    for url in [
        "https://api.hh.ru/openapi/redoc",
        "https://api.hh.ru/openapi/specification/public",
        "https://hh.ru/account/login",
    ]:
        try:
            with httpx.Client(proxy=proxy, timeout=15.0, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"}) as c:
                r = c.get(url)
                print(f"  {url.replace('https://', '')}: {r.status_code} ({len(r.text)} chars)")
        except Exception as e:
            print(f"  {url}: ERROR {e}")

    # Save vacancy and employer 403 samples
    status, body = req_proxy(proxy, "https://api.hh.ru/vacancies", {"text": "computer vision", "per_page": 5, "area": "1"})
    (SAMPLES_DIR / "10_vacancies_403_proxy.json").write_text(
        json.dumps({"status": status, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved vacancies 403 sample")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
