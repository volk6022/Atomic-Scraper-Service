"""
avito_httpx_probe.py — probe avito.ru vacancies page with httpx.

Attempt order:
  (a) direct (no proxy)
  (b) via RU residential proxy (rotating, puls-proxy)

Saves HTML / error evidence to experiment-avito/samples/.

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-avito\\avito_httpx_probe.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

PROXIES_FILE = Path(__file__).parent.parent / "proxies.txt"

URLS = [
    "https://www.avito.ru/all/vakansii",
    "https://www.avito.ru/moskva/vakansii",
    "https://www.avito.ru/sankpeterburg/vakansii",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# ---------------------------------------------------------------------------
# Proxy loading
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_proxies() -> list[str]:
    if not PROXIES_FILE.exists():
        return []
    proxies = []
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            enc_user = urllib.parse.quote(m.group("user"), safe="")
            enc_pass = urllib.parse.quote(m.group("password"), safe="")
            proxies.append(f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}")
    return proxies


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_embedded_json(html: str) -> dict:
    """Try to extract window.__initialData__ or similar embedded JSON blobs."""
    results = {}

    # Pattern 1: window.__initialData__ = {...}
    m = re.search(r'window\.__initialData__\s*=\s*(\{.{100,}?\});?\s*\n', html, re.DOTALL)
    if m:
        try:
            results["__initialData__"] = json.loads(m.group(1))
        except Exception as e:
            results["__initialData___raw"] = m.group(1)[:500]
            results["__initialData___err"] = str(e)

    # Pattern 2: window.__INITIAL_STATE__ = {...}
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.{100,}?\});?\s*\n', html, re.DOTALL)
    if m:
        try:
            results["__INITIAL_STATE__"] = json.loads(m.group(1))
        except Exception as e:
            results["__INITIAL_STATE___raw"] = m.group(1)[:500]

    # Pattern 3: <script type="application/json" ...> blobs
    for sm in re.finditer(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            blob = json.loads(sm.group(1))
            results.setdefault("script_json_blobs", []).append(blob)
        except Exception:
            pass

    # Pattern 4: data-state attribute JSON
    m = re.search(r'data-state=["\'](\{.{50,}?\})["\']', html)
    if m:
        try:
            results["data_state"] = json.loads(m.group(1))
        except Exception:
            results["data_state_raw"] = m.group(1)[:300]

    # Pattern 5: search for item IDs in JSON-like structures
    item_ids = re.findall(r'"itemId"\s*:\s*(\d+)', html)
    if not item_ids:
        item_ids = re.findall(r'"id"\s*:\s*(\d{8,12})', html)
    results["item_ids_found"] = item_ids[:20]

    return results


def classify_response(status: int, html: str, url: str) -> str:
    """Classify the response as REAL_CONTENT / BLOCKED / CHALLENGE / REDIRECT."""
    if status == 200:
        low = html.lower()
        if "доступ с вашего ip-адреса временно ограничен" in low:
            return "IP_BLOCKED"
        if "datadome" in low or "dd_cookie" in low:
            return "DATADOME_CHALLENGE"
        if "checking your browser" in low or "пожалуйста, подождите" in low:
            return "JS_CHALLENGE"
        if len(html) < 5000:
            return "TOO_SHORT_SUSPICIOUS"
        if "vakansii" in low or "вакансии" in low or "работа" in low:
            return "REAL_CONTENT"
        return "UNKNOWN_200"
    if status in (301, 302, 303, 307, 308):
        return f"REDIRECT_{status}"
    if status == 403:
        return "HTTP_403"
    if status == 429:
        return "RATE_LIMITED_429"
    if status == 503:
        return "SERVICE_UNAVAILABLE_503"
    return f"HTTP_{status}"


# ---------------------------------------------------------------------------
# Main probe
# ---------------------------------------------------------------------------

def probe_url(url: str, proxy_url: str | None = None, timeout: float = 25.0) -> dict:
    label = f"{'proxy' if proxy_url else 'direct'}"
    proxy_arg = proxy_url  # httpx accepts proxy= as URL string

    print(f"\n  [{label}] GET {url}")
    t0 = time.time()
    try:
        with httpx.Client(
            proxy=proxy_arg,
            headers=HEADERS,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            elapsed = time.time() - t0
            html = resp.text
            verdict = classify_response(resp.status_code, html, url)
            print(f"  [{label}] HTTP {resp.status_code} | {len(html)} chars | {elapsed:.1f}s | verdict={verdict}")
            return {
                "url": url,
                "proxy": label,
                "status": resp.status_code,
                "html_len": len(html),
                "elapsed": round(elapsed, 2),
                "verdict": verdict,
                "html_snippet": html[:3000],
                "final_url": str(resp.url),
            }
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"  [{label}] ERROR {type(exc).__name__}: {exc} ({elapsed:.1f}s)")
        return {
            "url": url,
            "proxy": label,
            "status": None,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": round(elapsed, 2),
            "verdict": "CONNECTION_ERROR",
        }


def main():
    proxies = load_proxies()
    print(f"Loaded {len(proxies)} proxies")

    results = []
    target_url = URLS[0]  # avito.ru/all/vakansii

    # (a) direct
    r_direct = probe_url(target_url, proxy_url=None)
    results.append(r_direct)

    direct_html = r_direct.get("html_snippet", "")
    if r_direct["verdict"] == "REAL_CONTENT":
        print("\n  Direct worked! Extracting embedded JSON...")
        full_resp = None
        try:
            with httpx.Client(headers=HEADERS, timeout=25, follow_redirects=True) as c:
                full_resp = c.get(target_url)
        except Exception:
            pass
        if full_resp:
            extracted = extract_embedded_json(full_resp.text)
            r_direct["embedded_json"] = extracted
            (SAMPLES_DIR / "avito_direct_page.html").write_text(full_resp.text, encoding="utf-8")
            print(f"  Saved HTML: {SAMPLES_DIR / 'avito_direct_page.html'}")
    else:
        print(f"\n  Direct blocked ({r_direct['verdict']}). Saving snippet...")
        (SAMPLES_DIR / "avito_direct_blocked.html").write_text(
            r_direct.get("html_snippet", "NO CONTENT"), encoding="utf-8"
        )

    # (b) via RU proxy
    if proxies:
        import random
        proxy_pool = proxies[:]
        random.shuffle(proxy_pool)
        proxy_success = False
        for proxy_url in proxy_pool[:5]:  # try up to 5
            r_proxy = probe_url(target_url, proxy_url=proxy_url)
            results.append(r_proxy)
            if r_proxy["verdict"] == "REAL_CONTENT":
                print("\n  Proxy worked! Extracting embedded JSON...")
                try:
                    with httpx.Client(proxy=proxy_url, headers=HEADERS, timeout=25, follow_redirects=True) as c:
                        full_resp = c.get(target_url)
                    extracted = extract_embedded_json(full_resp.text)
                    r_proxy["embedded_json"] = extracted
                    (SAMPLES_DIR / "avito_proxy_page.html").write_text(full_resp.text, encoding="utf-8")
                    print(f"  Saved HTML: {SAMPLES_DIR / 'avito_proxy_page.html'}")
                except Exception as e:
                    print(f"  Could not re-fetch for extraction: {e}")
                proxy_success = True
                break
            elif r_proxy["verdict"] not in ("CONNECTION_ERROR",):
                # Got a response (blocked but not a conn error) — save it
                (SAMPLES_DIR / "avito_proxy_blocked.html").write_text(
                    r_proxy.get("html_snippet", "NO CONTENT"), encoding="utf-8"
                )
                break

    # Save all results
    ev_path = SAMPLES_DIR / "avito_httpx_evidence.json"
    ev_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidence saved: {ev_path}")

    # Summary
    print("\n=== SUMMARY ===")
    for r in results:
        proxy_lbl = r.get("proxy", "?")
        verdict = r.get("verdict", "?")
        status = r.get("status", "err")
        elapsed = r.get("elapsed", "?")
        print(f"  [{proxy_lbl}] status={status} verdict={verdict} elapsed={elapsed}s")


if __name__ == "__main__":
    main()
