"""
test_with_hh_useragent.py — Try the official HH app User-Agent format
and check what IP the API sees.

HH official docs say User-Agent must be: "YourApplicationName/1.0 (your-contact@example.com)"
The 403 with {"type":"forbidden"} is documented as CAPTCHA required.

Key question: does this mean ALL anonymous API requests get captcha now?
Or only certain IPs?

Tests:
1. Check actual outgoing IP via ip-api / ifconfig.me
2. Check outgoing IP through proxy
3. Try the HH API /vacancies with User-Agent in the official format
4. Try with HH-User-Agent header (some apps use this)
5. Check the captcha_url in the 403 response
6. Try a Playwright-based request (stealth) to see if that bypasses captcha
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


def check_ip(proxy: str | None = None) -> str:
    try:
        with httpx.Client(proxy=proxy, timeout=10.0) as c:
            r = c.get("https://api.ipify.org?format=json")
            return r.json().get("ip", "?")
    except Exception as e:
        return f"ERROR: {e}"


def try_hh_vacancies(label: str, proxy: str | None, extra_headers: dict | None = None) -> dict:
    headers = {
        "User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)",
        "Accept": "application/json",
        **(extra_headers or {}),
    }
    try:
        with httpx.Client(proxy=proxy, timeout=20.0, follow_redirects=True, headers=headers) as c:
            # First get cookies from root
            r0 = c.get("https://api.hh.ru/")
            r1 = c.get("https://api.hh.ru/vacancies",
                       params={"text": "python", "per_page": 5, "area": "1"})
            result = {
                "label": label,
                "root_status": r0.status_code,
                "vacancies_status": r1.status_code,
                "vacancies_body": r1.text[:500],
                "vacancies_headers": dict(r1.headers),
            }
            # Check if 403 has captcha_url
            if r1.status_code == 403:
                try:
                    body = r1.json()
                    for err in body.get("errors", []):
                        if "captcha_url" in err:
                            result["captcha_url"] = err["captcha_url"]
                except Exception:
                    pass
            return result
    except Exception as e:
        return {"label": label, "error": str(e)}


def main():
    proxies = load_proxies()

    print("=== IP Check ===")
    direct_ip = check_ip(None)
    print(f"  Direct IP: {direct_ip}")

    # Find working proxies
    working_proxies = []
    for p in proxies[:40]:
        try:
            with httpx.Client(proxy=p, timeout=8.0) as c:
                r = c.get("https://api.hh.ru/dictionaries")
                if r.status_code == 200:
                    ip = check_ip(p)
                    print(f"  Proxy {p.split('@')[-1]}: works, IP={ip}")
                    working_proxies.append((p, ip))
                    if len(working_proxies) >= 5:
                        break
        except Exception:
            pass

    all_results = []

    # Test direct
    print("\n=== Direct requests ===")
    r = try_hh_vacancies("Direct standard UA", None)
    print(f"  vacancies status: {r.get('vacancies_status')}")
    if "captcha_url" in r:
        print(f"  captcha_url: {r['captcha_url'][:200]}")
    all_results.append(r)

    # Test with each working proxy
    print("\n=== Proxy requests ===")
    for (p, ip) in working_proxies[:3]:
        r = try_hh_vacancies(f"Proxy {p.split('@')[-1]} (IP={ip})", p)
        print(f"  [{r['label']}] vacancies status: {r.get('vacancies_status')}")
        if "captcha_url" in r:
            print(f"    captcha_url: {r['captcha_url'][:200]}")
        all_results.append(r)

    # Try with explicit Accept-Language and Referer (to look more browser-like)
    if working_proxies:
        p, ip = working_proxies[0]
        r2 = try_hh_vacancies(
            "Proxy browser-like headers",
            p,
            extra_headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://hh.ru/",
                "Origin": "https://hh.ru",
            }
        )
        print(f"  [Browser-like] vacancies status: {r2.get('vacancies_status')}")
        if "captcha_url" in r2:
            print(f"    captcha_url: {r2['captcha_url'][:200]}")
        all_results.append(r2)

    # Save results
    save_path = SAMPLES_DIR / "08_captcha_diagnosis.json"
    # Strip headers from saved results to keep it clean
    for r in all_results:
        r.pop("vacancies_headers", None)
    save_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {save_path.name}")
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
