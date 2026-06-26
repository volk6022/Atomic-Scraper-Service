"""
diagnose_403_v2.py — deeper investigation.

The 403 on /vacancies appears despite /dictionaries returning 200.
Server is ddos-guard (not Cloudflare).

Theories to test:
1. Minimal Accept header mismatch
2. HH-specific User-Agent header format requirement
3. Whether /vacancies/{id} also 403s
4. Whether the 403 body has more detail with different Accept
5. Try /vacancies with Accept: text/html to see if that differs
6. Try the openapi spec endpoint
7. Check if there's a cookie requirement from the / endpoint
8. Try /professional_roles (worked before)
9. Try /vacancies with a session cookie obtained from /
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


def find_working_proxy(proxies: list[str], test_url: str = "https://api.hh.ru/dictionaries") -> str | None:
    for p in proxies:
        try:
            with httpx.Client(proxy=p, timeout=15.0, follow_redirects=True,
                              headers={"User-Agent": "test/1.0"}) as c:
                r = c.get(test_url)
            if r.status_code < 500:
                print(f"  Found working proxy: {p.split('@')[-1]}")
                return p
        except Exception:
            pass
    return None


def test(label: str, url: str, proxy: str | None, headers: dict | None = None,
         params: dict | None = None, cookies: dict | None = None) -> httpx.Response | None:
    try:
        with httpx.Client(
            proxy=proxy,
            timeout=20.0,
            follow_redirects=True,
            headers=headers or {},
            cookies=cookies or {},
        ) as c:
            r = c.get(url, params=params)
        status = r.status_code
        ct = r.headers.get("content-type", "")
        body_preview = r.text[:300] if status != 200 else r.text[:150]
        print(f"  [{label}] {status}  {ct}")
        if status != 200:
            print(f"    body: {body_preview}")
        else:
            print(f"    ok, body[:150]: {body_preview}")
        return r
    except Exception as e:
        print(f"  [{label}] ERROR: {type(e).__name__}: {str(e)[:100]}")
        return None


def main():
    proxies = load_proxies()

    print("=== Phase 1: Find working proxies ===")
    proxy1 = find_working_proxy(proxies[:30])
    proxy2 = None
    if proxy1:
        # find a second working proxy
        used_idx = next((i for i, p in enumerate(proxies[:30]) if p == proxy1), 0)
        proxy2 = find_working_proxy(proxies[used_idx+1:used_idx+30])

    print(f"\n=== Phase 2: Identify /vacancies 403 cause ===")
    print("--- Direct (no proxy) ---")

    # Direct: get session cookies from / first
    root_cookies = {}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible)"}) as c:
            r_root = c.get("https://api.hh.ru/")
            root_cookies = dict(r_root.cookies)
            print(f"  api root: {r_root.status_code}, cookies set: {list(root_cookies.keys())}")
    except Exception as e:
        print(f"  api root direct: ERROR {e}")

    # 1. Direct vacancies - minimal
    test("Direct /vacancies minimal UA", "https://api.hh.ru/vacancies",
         proxy=None,
         headers={"User-Agent": "my-app/1.0 (my@email.com)"},
         params={"text": "python", "per_page": 3})

    # 2. Direct vacancies - with root cookies
    test("Direct /vacancies + root cookies", "https://api.hh.ru/vacancies",
         proxy=None,
         headers={"User-Agent": "Mozilla/5.0"},
         params={"text": "python", "per_page": 3},
         cookies=root_cookies)

    # 3. Direct vacancies - with hhtoken cookie from root
    if root_cookies.get("hhtoken"):
        test("Direct /vacancies + hhtoken", "https://api.hh.ru/vacancies",
             proxy=None,
             headers={"User-Agent": "Mozilla/5.0",
                      "Cookie": f"hhtoken={root_cookies['hhtoken']}"},
             params={"text": "python", "per_page": 3})

    # 4. Direct: /professional_roles (this worked via proxy before)
    test("Direct /professional_roles", "https://api.hh.ru/professional_roles",
         proxy=None,
         headers={"User-Agent": "HHTest/1.0 (test@test.com)"})

    # 5. Direct: /vacancies/{id} — try a known vacancy id
    test("Direct /vacancies/102776520", "https://api.hh.ru/vacancies/102776520",
         proxy=None,
         headers={"User-Agent": "Mozilla/5.0"})

    # 6. Full session: get cookies from root, then use with vacancies
    print("\n--- Full session approach (direct) ---")
    try:
        with httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as c:
            r0 = c.get("https://api.hh.ru/")
            print(f"  Session GET / → {r0.status_code}, cookies: {list(c.cookies.keys())}")
            r1 = c.get("https://api.hh.ru/vacancies", params={"text": "python", "per_page": 5})
            print(f"  Session GET /vacancies → {r1.status_code}")
            if r1.status_code != 200:
                print(f"  body: {r1.text[:300]}")
            else:
                data = r1.json()
                print(f"  found={data.get('found')}, items={len(data.get('items', []))}")
                save_path = SAMPLES_DIR / "01_vacancy_search.json"
                save_path.write_text(json.dumps({
                    "found": data.get("found"),
                    "pages": data.get("pages"),
                    "per_page": data.get("per_page"),
                    "items_count": len(data.get("items", [])),
                    "first_item_fields": sorted(data["items"][0].keys()) if data.get("items") else [],
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Saved sample 01_vacancy_search.json")
    except Exception as e:
        print(f"  Session approach ERROR: {e}")

    if proxy1:
        print(f"\n--- Proxy {proxy1.split('@')[-1]} ---")

        # Get cookies from / via proxy, then use them for /vacancies
        print("  Full session via proxy:")
        try:
            with httpx.Client(
                proxy=proxy1,
                timeout=25.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            ) as c:
                r0 = c.get("https://api.hh.ru/")
                print(f"  Proxy GET / → {r0.status_code}, cookies: {list(c.cookies.keys())}")
                r1 = c.get("https://api.hh.ru/vacancies", params={"text": "python", "per_page": 5})
                print(f"  Proxy GET /vacancies → {r1.status_code}")
                if r1.status_code != 200:
                    print(f"  body: {r1.text[:300]}")
                else:
                    data = r1.json()
                    print(f"  found={data.get('found')}, items={len(data.get('items', []))}")
        except Exception as e:
            print(f"  Proxy session ERROR: {type(e).__name__}: {e}")

        # Try /vacancies/{id} via proxy
        test("Proxy /vacancies/102776520", "https://api.hh.ru/vacancies/102776520",
             proxy=proxy1,
             headers={"User-Agent": "Mozilla/5.0"})

        # Try /employers via proxy
        test("Proxy /employers/1057", "https://api.hh.ru/employers/1057",
             proxy=proxy1,
             headers={"User-Agent": "Mozilla/5.0"})

    print("\n=== Phase 3: openapi spec ===")
    test("Direct openapi spec", "https://api.hh.ru/openapi/specification/public",
         proxy=None,
         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

    # Check vacancy_search_order from dictionaries via direct
    print("\n=== Phase 4: dictionaries for order_by values (direct) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "HHTest/1.0 (test@test.com)"}) as c:
            r = c.get("https://api.hh.ru/dictionaries")
        print(f"  /dictionaries → {r.status_code}")
        if r.status_code == 200:
            dicts = r.json()
            order_vals = dicts.get("vacancy_search_order", [])
            print(f"  vacancy_search_order: {[v.get('id') for v in order_vals]}")
            # Save
            (SAMPLES_DIR / "02b_vacancy_search_order_values.json").write_text(
                json.dumps(order_vals, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Saved 02b_vacancy_search_order_values.json")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
