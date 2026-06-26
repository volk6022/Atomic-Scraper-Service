"""
kwork_analyze_html.py — fetch the full projects page via httpx and analyze structure.
Also probes: project card, category endpoint, page param.

Run from repo root:
  uv run python experiment-kwork/kwork_analyze_html.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SAMPLES_DIR = Path(__file__).parent / "samples" / "httpx"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


def fetch(url: str, extra_headers: dict | None = None) -> httpx.Response:
    h = dict(HEADERS)
    if extra_headers:
        h.update(extra_headers)
    with httpx.Client(headers=h, follow_redirects=True, timeout=25.0) as c:
        return c.get(url)


def analyze_projects_page(html: str) -> dict:
    result: dict = {}

    # Project links: /projects/{id}/view
    project_ids = re.findall(r'/projects/(\d{4,})/view', html)
    result["project_id_count"] = len(set(project_ids))
    result["sample_project_ids"] = list(set(project_ids))[:15]

    # Want IDs in JSON
    want_ids = re.findall(r'"want_id"\s*:\s*(\d+)', html)
    result["want_id_count"] = len(set(want_ids))
    result["sample_want_ids"] = list(set(want_ids))[:15]

    # Titles via JSON
    titles = re.findall(r'"name"\s*:\s*"([^"]{10,200})"', html)
    result["titles_found"] = titles[:10]

    # Price/budget
    prices = re.findall(r'"price(?:_from|_to|From|To)?"\s*:\s*(\d+)', html)
    result["prices_found"] = prices[:10]

    # Category IDs
    cat_ids_1 = re.findall(r'"cat_id"\s*:\s*(\d+)', html)
    cat_ids_2 = re.findall(r'"category_id"\s*:\s*(\d+)', html)
    cat_ids_3 = re.findall(r'catId=(\d+)', html)
    cat_ids_4 = re.findall(r'"categoryId"\s*:\s*(\d+)', html)
    result["category_ids"] = list(set(cat_ids_1 + cat_ids_2 + cat_ids_3 + cat_ids_4))[:20]

    # Check for category names in HTML
    cat_names = re.findall(r'(?:Программирование|Python|ML|Искусственный|Машинное|Нейросети)[^\n<"]{0,80}', html)
    result["category_name_hints"] = list(set(cat_names))[:10]

    # Check for pagination in HTML
    result["page_param_in_html"] = "?page=" in html or "&page=" in html
    result["pagination_element"] = bool(re.search(r'class=["\'][^"\']*pagina', html))

    # Window globals
    globals_m = re.findall(r'window\.([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(\{[^;]{0,300})', html)
    result["window_globals"] = [f"window.{k}" for k, _ in globals_m[:10]]

    # Server-rendered project data (look for JSON blobs near project cards)
    json_data_m = re.search(r'var\s+wantsData\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
    if not json_data_m:
        json_data_m = re.search(r'wantsData\s*:\s*(\{[^}]{20,})', html)
    result["wants_data_blob"] = bool(json_data_m)

    # Look for any inline JSON array with project objects
    # Pattern: {"id":NNN,"name":"...","price":...}
    inline_projects = re.findall(
        r'\{"id"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"([^"]{5,200})"', html
    )
    result["inline_json_projects"] = [
        {"id": m[0], "name": m[1]} for m in inline_projects[:10]
    ]

    # Look for /api/ URLs in JS
    api_urls = re.findall(r'["\'](?:/api/[^"\'?\s]{3,80})["\']', html)
    result["api_urls_in_js"] = list(set(api_urls))[:20]

    # Script tags loading JS
    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
    result["script_count"] = len(script_srcs)

    return result


if __name__ == "__main__":
    # 1. Fetch main projects page
    print("Fetching https://kwork.ru/projects ...")
    resp = fetch("https://kwork.ru/projects")
    html = resp.text
    print(f"  status={resp.status_code}  server={resp.headers.get('server','')}  length={len(html)}")

    # Save full HTML
    full_html_path = SAMPLES_DIR / "kwork_projects_full.html"
    full_html_path.write_text(html, encoding="utf-8")
    print(f"  Saved full HTML: {full_html_path}")

    analysis = analyze_projects_page(html)
    print(f"\n--- Projects page analysis ---")
    print(f"  project_id_count={analysis['project_id_count']}")
    print(f"  sample_project_ids={analysis['sample_project_ids'][:5]}")
    print(f"  want_id_count={analysis['want_id_count']}")
    print(f"  titles_found={analysis['titles_found'][:3]}")
    print(f"  prices_found={analysis['prices_found'][:3]}")
    print(f"  category_ids={analysis['category_ids'][:10]}")
    print(f"  category_name_hints={analysis['category_name_hints'][:3]}")
    print(f"  page_param_in_html={analysis['page_param_in_html']}")
    print(f"  pagination_element={analysis['pagination_element']}")
    print(f"  window_globals={analysis['window_globals'][:5]}")
    print(f"  wants_data_blob={analysis['wants_data_blob']}")
    print(f"  inline_json_projects={analysis['inline_json_projects'][:3]}")
    print(f"  api_urls_in_js={analysis['api_urls_in_js'][:10]}")
    print(f"  script_count={analysis['script_count']}")

    # 2. Project card
    # First try to use one of the found IDs
    test_id = analysis["sample_project_ids"][0] if analysis["sample_project_ids"] else "3016173"
    card_url = f"https://kwork.ru/projects/{test_id}/view"
    print(f"\nFetching project card: {card_url} ...")
    resp2 = fetch(card_url)
    html2 = resp2.text
    print(f"  status={resp2.status_code}  length={len(html2)}")
    (SAMPLES_DIR / f"kwork_card_{test_id}.html").write_text(html2, encoding="utf-8")
    card_analysis = analyze_projects_page(html2)

    # Card-specific checks
    login_gate = (
        "войдите" in html2.lower()
        or "авторизуй" in html2.lower()
        or "войти" in html2.lower()
        or ("login" in html2.lower() and "redirect" in html2.lower())
    )
    h1_m = re.search(r'<h1[^>]*>([^<]{3,200})</h1>', html2)
    h1_text = h1_m.group(1).strip() if h1_m else ""
    budget_m = re.search(r'(?:price|budget|бюджет|₽)[^<>]{0,100}(\d[\d\s]+)(?:₽|руб|rub)', html2, re.IGNORECASE)
    cf_turnstile = "turnstile" in html2.lower() or "cf-turnstile" in html2.lower()

    print(f"  login_gate={login_gate}  h1={h1_text!r}")
    print(f"  turnstile={cf_turnstile}")
    print(f"  category_ids={card_analysis['category_ids'][:5]}")
    print(f"  titles_found={card_analysis['titles_found'][:2]}")
    print(f"  prices_found={card_analysis['prices_found'][:3]}")
    print(f"  budget_match={budget_m.group(0)[:50] if budget_m else 'none'}")

    # 3. Projects with page=2 (to see if SSR pages load or redirect)
    print(f"\nFetching https://kwork.ru/projects?page=2 ...")
    resp3 = fetch("https://kwork.ru/projects?page=2")
    html3 = resp3.text
    analysis3 = analyze_projects_page(html3)
    print(f"  status={resp3.status_code}  url={str(resp3.url)}  length={len(html3)}")
    print(f"  project_ids_p2={analysis3['sample_project_ids'][:5]}")
    print(f"  different_from_p1={set(analysis3['sample_project_ids']) != set(analysis['sample_project_ids'])}")

    # 4. Try XHR-style endpoint guesses
    # Based on report's mention of internal API
    xhr_candidates = [
        ("GET", "https://kwork.ru/api/projects"),
        ("POST", "https://kwork.ru/api/projects"),
        ("GET", "https://kwork.ru/api/projects/list"),
        ("GET", "https://kwork.ru/projects/list"),
        ("POST", "https://kwork.ru/projects"),
        ("GET", "https://kwork.ru/api/offer/want-list"),
        ("GET", "https://kwork.ru/api/want/list"),
    ]
    print("\n--- XHR endpoint probes ---")
    xhr_results = []
    for method, xurl in xhr_candidates:
        try:
            with httpx.Client(
                headers={
                    **HEADERS,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": "https://kwork.ru/projects",
                },
                follow_redirects=True,
                timeout=15.0,
            ) as c:
                if method == "GET":
                    r = c.get(xurl)
                else:
                    r = c.post(xurl, json={})
            snippet = r.text[:300]
            is_json = r.headers.get("content-type", "").startswith("application/json")
            print(f"  {method} {xurl} -> {r.status_code} json={is_json} snippet={snippet[:100]!r}")
            xhr_results.append({
                "method": method,
                "url": xurl,
                "status": r.status_code,
                "is_json": is_json,
                "content_type": r.headers.get("content-type", ""),
                "body_preview": snippet,
            })
        except Exception as exc:
            print(f"  {method} {xurl} -> ERROR: {exc}")
            xhr_results.append({"method": method, "url": xurl, "error": str(exc)})

    # Save all evidence
    evidence = {
        "projects_page": {
            "status": resp.status_code,
            "server": resp.headers.get("server", ""),
            "html_length": len(html),
            "analysis": analysis,
        },
        "card_probe": {
            "url": card_url,
            "id": test_id,
            "status": resp2.status_code,
            "html_length": len(html2),
            "login_gate": login_gate,
            "h1_text": h1_text,
            "cf_turnstile": cf_turnstile,
            "analysis": card_analysis,
        },
        "page2_probe": {
            "status": resp3.status_code,
            "final_url": str(resp3.url),
            "html_length": len(html3),
            "project_ids": analysis3["sample_project_ids"],
            "different_from_page1": (
                set(analysis3["sample_project_ids"]) != set(analysis["sample_project_ids"])
            ),
        },
        "xhr_candidates": xhr_results,
    }
    ev_path = SAMPLES_DIR / "analysis_evidence.json"
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"\nFull analysis saved: {ev_path}")
