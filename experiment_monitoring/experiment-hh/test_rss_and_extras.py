"""
test_rss_and_extras.py

Final evidence gathering:
1. RSS feed test
2. Cloudflare/DDoS-Guard detection on HTML site
3. Save all available schema data from OpenAPI spec
4. Summarize what we know about the 403 error type
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


def find_proxy(proxies: list[str]) -> str | None:
    for p in proxies[:50]:
        try:
            with httpx.Client(proxy=p, timeout=8.0) as c:
                r = c.get("https://api.hh.ru/dictionaries")
                if r.status_code == 200:
                    return p
        except Exception:
            pass
    return None


def main():
    proxies = load_proxies()
    proxy = find_proxy(proxies)
    print(f"Working proxy: {proxy.split('@')[-1] if proxy else 'none'}")

    # 1. RSS test (direct — no proxy for hh.ru HTML)
    print("\n=== RSS feed test (direct) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                   "Accept": "application/rss+xml, text/xml, */*"}) as c:
            r = c.get("https://hh.ru/search/vacancy/rss",
                      params={"text": "machine+learning", "area": "1"})
            print(f"  Status: {r.status_code}")
            print(f"  Content-Type: {r.headers.get('content-type')}")
            print(f"  First 400 chars: {r.text[:400]}")
            (SAMPLES_DIR / "07_rss_check.json").write_text(json.dumps({
                "status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "snippet": r.text[:500],
                "is_xml": "<?xml" in r.text or "<rss" in r.text or "<feed" in r.text,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 2. HTML site test (Cloudflare / ddos-guard detection)
    print("\n=== HTML site access (direct, requests) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as c:
            r = c.get("https://hh.ru/vacancies")
            print(f"  Status: {r.status_code}")
            print(f"  Content-Type: {r.headers.get('content-type')}")
            server = r.headers.get("server", "?")
            print(f"  Server: {server}")
            # Check for anti-bot signals
            is_cloudflare = "cloudflare" in server.lower()
            is_ddosguard = "ddos-guard" in server.lower()
            has_challenge = "challenge" in r.text.lower() or "cf-challenge" in r.text.lower()
            print(f"  Cloudflare: {is_cloudflare}, DDoS-Guard: {is_ddosguard}, Challenge: {has_challenge}")
            print(f"  First 300 chars: {r.text[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 3. Full dictionaries sample
    print("\n=== Save full dictionaries sample (direct) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "HHMonitor/1.0 (vpncreatedakk@gmail.com)"}) as c:
            r = c.get("https://api.hh.ru/dictionaries")
            if r.status_code == 200:
                data = r.json()
                # Save trimmed version with just keys
                summary = {k: len(v) if isinstance(v, list) else v
                           for k, v in data.items()}
                (SAMPLES_DIR / "dictionaries_keys.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  /dictionaries keys: {list(data.keys())[:20]}")
                # Get vacancy_search_order
                vso = data.get("vacancy_search_order", [])
                print(f"  vacancy_search_order: {[v.get('id') for v in vso]}")
                # Save full dictionaries
                (SAMPLES_DIR / "02b_vacancy_search_order_values.json").write_text(
                    json.dumps(vso, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Saved vacancy_search_order sample")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 4. Check areas for Moscow code
    print("\n=== Area codes (direct) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "HHMonitor/1.0"}) as c:
            r = c.get("https://api.hh.ru/areas")
            if r.status_code == 200:
                data = r.json()
                # Find Russia and its major cities
                russia = next((a for a in data if a.get("name") == "Россия"), None)
                if russia:
                    print(f"  Russia id: {russia.get('id')}")
                    cities = russia.get("areas", [])
                    moscow = next((c for c in cities if "Москва" in c.get("name", "")), None)
                    spb = next((c for c in cities if "Санкт" in c.get("name", "")), None)
                    if moscow:
                        print(f"  Moscow: id={moscow.get('id')}, name={moscow.get('name')}")
                    if spb:
                        print(f"  SPb: id={spb.get('id')}, name={spb.get('name')}")
                (SAMPLES_DIR / "areas_sample.json").write_text(
                    json.dumps([{"id": a.get("id"), "name": a.get("name")} for a in data], ensure_ascii=False, indent=2),
                    encoding="utf-8")
                print(f"  Saved areas_sample.json ({len(data)} top-level areas)")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 5. Professional roles (direct)
    print("\n=== Professional roles (direct) ===")
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True,
                          headers={"User-Agent": "HHMonitor/1.0"}) as c:
            r = c.get("https://api.hh.ru/professional_roles")
            print(f"  Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                cats = data.get("categories", [])
                roles = []
                for cat in cats:
                    for role in cat.get("roles", []):
                        roles.append({"id": role["id"], "name": role["name"], "category": cat.get("name")})
                # ML-relevant
                ml_kw = {"ml", "machine", "learning", "vision", "data", "analyst",
                         "нейрон", "данных", "машин", "глубок", "компьютерн", "алгоритм"}
                ml_roles = [r for r in roles if any(kw in r["name"].lower() for kw in ml_kw)]
                (SAMPLES_DIR / "06_professional_roles_ml.json").write_text(
                    json.dumps({"total_roles": len(roles), "ml_relevant": ml_roles},
                               ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Total: {len(roles)} roles, ML-relevant: {len(ml_roles)}")
                for r2 in ml_roles:
                    name_safe = r2["name"]
                    print(f"    id={r2['id']} cat={r2['category']}: {name_safe}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
