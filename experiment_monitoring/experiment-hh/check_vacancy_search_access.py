"""
check_vacancy_search_access.py

Based on evidence so far:
- /dictionaries: 200 (works direct + proxy)
- /professional_roles: 200 (works direct + proxy)
- /vacancies: 403 {"type":"forbidden"} (fails direct + proxy)
- /vacancies/{id}: 403 (fails via proxy)
- /employers/{id}: 403 (fails via proxy)

This matches known HH API behavior since ~2023: anonymous access to /vacancies
REQUIRES a registered OAuth application. The "forbidden" error is not CAPTCHA
but rather "this endpoint requires an application token".

Per the official HH API docs (GitHub hhru/api):
"For accessing the API you must register an application and obtain
an application access token."

Let's verify this theory by checking:
1. The GitHub API docs for current access requirements
2. Try with a fake Authorization header to see if the error message changes
3. Try access_token param approach (some old HH APIs accepted query param)
4. Verify by looking at the full list of endpoints that work vs fail
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


def req(url: str, proxy: str | None = None, params: dict | None = None,
        headers: dict | None = None, timeout: float = 25.0) -> tuple[int, str]:
    h = {"Accept": "application/json", **(headers or {})}
    try:
        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=True, headers=h) as c:
            r = c.get(url, params=params or {})
            return r.status_code, r.text[:500]
    except Exception as e:
        return -1, str(e)[:200]


def main():
    proxies = load_proxies()
    proxy = find_proxy(proxies)
    print(f"Working proxy: {proxy.split('@')[-1] if proxy else 'none'}")

    print("\n=== Comprehensive endpoint access matrix ===")
    endpoints = [
        ("GET /", "https://api.hh.ru/", {}),
        ("GET /dictionaries", "https://api.hh.ru/dictionaries", {}),
        ("GET /areas", "https://api.hh.ru/areas", {}),
        ("GET /professional_roles", "https://api.hh.ru/professional_roles", {}),
        ("GET /specializations", "https://api.hh.ru/specializations", {}),
        ("GET /industries", "https://api.hh.ru/industries", {}),
        ("GET /vacancies (anon)", "https://api.hh.ru/vacancies", {"text": "python", "per_page": 5}),
        ("GET /vacancies (no params)", "https://api.hh.ru/vacancies", {}),
        ("GET /vacancies/{id} (known)", "https://api.hh.ru/vacancies/116855878", {}),
        ("GET /employers (search)", "https://api.hh.ru/employers", {"text": "yandex", "per_page": 5}),
        ("GET /employers/{id}", "https://api.hh.ru/employers/1057", {}),
        ("GET /me", "https://api.hh.ru/me", {}),
    ]

    results = []
    for label, url, params in endpoints:
        status, body = req(url, proxy, params)
        ok_mark = "OK" if status == 200 else f"FAIL({status})"
        print(f"  {ok_mark}  {label}")
        if status not in (200, -1):
            try:
                err = json.loads(body)
                errors = err.get("errors", [])
                for e in errors:
                    print(f"         error: {e}")
            except Exception:
                print(f"         body: {body[:100]}")
        results.append({"label": label, "url": url, "status": status, "body_snippet": body[:200]})

    (SAMPLES_DIR / "11_endpoint_access_matrix.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Try Authorization header ===")
    # Test if a fake/dummy Bearer token changes the error
    for bearer in ["dummy_token", "client_credentials", ""]:
        auth_header = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        status, body = req(
            "https://api.hh.ru/vacancies",
            proxy,
            {"text": "python", "per_page": 3},
            headers={"User-Agent": "test/1.0", **auth_header},
        )
        print(f"  Bearer '{bearer}': {status} — {body[:200]}")

    print("\n=== Check vacancies via /vacancies?employer_id=1057 (employer's vacancies) ===")
    status, body = req("https://api.hh.ru/vacancies", proxy, {"employer_id": "1057", "per_page": 5})
    print(f"  employer_id filter: {status} — {body[:200]}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
