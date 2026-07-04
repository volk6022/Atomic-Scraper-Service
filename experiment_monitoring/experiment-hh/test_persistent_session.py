"""
test_persistent_session.py

The 403 {"type":"forbidden"} on /vacancies is the CAPTCHA trigger.
Per the OpenAPI spec, the 403 on /vacancies includes a captcha_url
that the app must redirect to so the user can solve the CAPTCHA.

After solving the CAPTCHA, the cookie is set and subsequent requests work.

This test:
1. Gets the full 403 response body to find captcha_url
2. Tries different approaches to see if any bypass the captcha requirement
3. Tests /vacancies through httpx.AsyncClient with longer timeout
4. Tests what happens with a proper Accept header
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


def get_full_403(proxy: str | None = None) -> dict:
    """Get the full 403 response body to find captcha_url."""
    try:
        with httpx.Client(proxy=proxy, timeout=30.0, follow_redirects=True,
                          headers={"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)",
                                   "Accept": "application/json"}) as c:
            r = c.get("https://api.hh.ru/vacancies",
                      params={"text": "python", "per_page": 5})
            body_text = r.text
            try:
                body_json = r.json()
            except Exception:
                body_json = {"raw": body_text[:500]}
            return {
                "status": r.status_code,
                "body": body_json,
                "headers": dict(r.headers),
                "proxy": proxy.split("@")[-1] if proxy else "direct",
            }
    except Exception as e:
        return {"error": str(e), "proxy": proxy.split("@")[-1] if proxy else "direct"}


def try_with_longer_timeout(proxy: str, timeout: float = 45.0) -> dict:
    """Try with a much longer timeout — the proxy may be slow for /vacancies."""
    try:
        with httpx.Client(
            proxy=proxy,
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=5.0),
            follow_redirects=True,
            headers={"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)",
                     "Accept": "application/json"}
        ) as c:
            # warm up with dictionaries
            r0 = c.get("https://api.hh.ru/dictionaries")
            print(f"    dictionaries: {r0.status_code}")
            # now try vacancies
            r1 = c.get("https://api.hh.ru/vacancies",
                       params={"text": "python", "per_page": 5})
            return {"status": r1.status_code, "body": r1.text[:500]}
    except Exception as e:
        return {"error": str(e)}


def main():
    proxies = load_proxies()

    print("=== Step 1: Full 403 response body (direct) ===")
    r403 = get_full_403(None)
    print(f"  Status: {r403.get('status')}")
    print(f"  Body: {json.dumps(r403.get('body', {}), ensure_ascii=False)[:600]}")
    errors = r403.get("body", {}).get("errors", [])
    for e in errors:
        if "captcha_url" in e:
            print(f"  captcha_url: {e['captcha_url']}")
        print(f"  error type: {e.get('type')}, value: {e.get('value')}")

    # Save
    (SAMPLES_DIR / "09_full_403_response.json").write_text(
        json.dumps(r403, ensure_ascii=False, indent=2), encoding="utf-8")

    # Find working proxies that can do dictionaries
    print("\n=== Step 2: Find proxies that get past ddos-guard ===")
    working = []
    for p in proxies[:50]:
        try:
            with httpx.Client(proxy=p, timeout=12.0, follow_redirects=True,
                              headers={"User-Agent": "test/1.0"}) as c:
                r = c.get("https://api.hh.ru/dictionaries")
                if r.status_code == 200:
                    working.append(p)
                    print(f"  OK: {p.split('@')[-1]}")
                    if len(working) >= 5:
                        break
                elif r.status_code not in (407, 500, 502, 503):
                    print(f"  {r.status_code}: {p.split('@')[-1]}")
        except Exception:
            pass
    print(f"  Found {len(working)} working proxies")

    # For each working proxy, get full 403 response
    print("\n=== Step 3: 403 body via proxy ===")
    for p in working[:3]:
        r = get_full_403(p)
        print(f"  {r['proxy']}: status={r.get('status')}, error={r.get('error', 'none')}")
        body = r.get("body", {})
        print(f"    body: {json.dumps(body, ensure_ascii=False)[:400]}")
        errors = body.get("errors", [])
        for e in errors:
            if "captcha_url" in e:
                print(f"    captcha_url: {e['captcha_url'][:200]}")

    # Try with longer timeout
    print("\n=== Step 4: /vacancies with 45s timeout via proxy ===")
    if working:
        for p in working[:3]:
            print(f"  Trying {p.split('@')[-1]}...")
            result = try_with_longer_timeout(p, timeout=45.0)
            print(f"  Result: {result}")

    # Test: what about /vacancies/search specifically?
    print("\n=== Step 5: Alternate endpoints ===")
    if working:
        p = working[0]
        endpoints = [
            "/vacancies",
            "/vacancies?text=python&per_page=5",
        ]
        with httpx.Client(proxy=p, timeout=30.0, follow_redirects=True,
                          headers={"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)",
                                   "Accept": "application/json"}) as c:
            # Try getting main page cookies
            c.get("https://hh.ru/")
            c.get("https://api.hh.ru/")

            for url in [
                "https://api.hh.ru/vacancies",
                "https://api.hh.ru/vacancies/102776520",
                "https://api.hh.ru/employers/1057",
            ]:
                try:
                    r = c.get(url, params={"text": "python", "per_page": 5} if "vacancies" in url and "{" not in url else {})
                    print(f"  {url.replace('https://api.hh.ru','')}  → {r.status_code}")
                    if r.status_code == 403:
                        body = r.json()
                        errors = body.get("errors", [])
                        for e in errors:
                            print(f"    error: type={e.get('type')}, captcha_url={e.get('captcha_url', 'n/a')[:100]}")
                    elif r.status_code == 200:
                        data = r.json()
                        print(f"    OK: {list(data.keys())[:10]}")
                except Exception as ex:
                    print(f"  {url}  → ERROR: {ex}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
