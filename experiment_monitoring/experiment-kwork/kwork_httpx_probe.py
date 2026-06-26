"""
kwork_httpx_probe.py — Step (a)+(b): httpx direct & via proxy for kwork.ru

Tests:
  (a) httpx direct — status, anti-bot headers (CF-RAY, DDoS-Guard), body shape
  (b) httpx via RU proxy — same checks

Saves evidence to experiment-kwork/samples/httpx/

Run from repo root:
  cd "...\\Atomic-Scraper-Service"
  uv run python experiment-kwork\\kwork_httpx_probe.py
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
SAMPLES_DIR = Path(__file__).parent / "samples" / "httpx"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

PROXIES_FILE = Path(__file__).parent.parent / "proxies.txt"

TARGET_URL = "https://kwork.ru/projects"
CARD_URL_TEMPLATE = "https://kwork.ru/projects/{}/view"

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
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# ---------------------------------------------------------------------------


def load_proxies() -> list[str]:
    _LINE_RE = re.compile(
        r"^https?://"
        r"(?P<user>[^:@]+)"
        r":"
        r"(?P<password>[^@]+)"
        r"@"
        r"(?P<host>[^:]+)"
        r":"
        r"(?P<port>\d+)$"
    )
    proxies: list[str] = []
    if not PROXIES_FILE.exists():
        return proxies
    for raw_line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        enc_user = urllib.parse.quote(m.group("user"), safe="")
        enc_pass = urllib.parse.quote(m.group("password"), safe="")
        proxies.append(f"http://{enc_user}:{enc_pass}@{m.group('host')}:{m.group('port')}")
    return proxies


def detect_antibot(resp: httpx.Response) -> dict:
    headers = dict(resp.headers)
    body = resp.text[:4000] if hasattr(resp, "text") else ""
    result: dict = {
        "status": resp.status_code,
        "cf_ray": headers.get("cf-ray", ""),
        "cf_cache_status": headers.get("cf-cache-status", ""),
        "server": headers.get("server", ""),
        "x_powered_by": headers.get("x-powered-by", ""),
        "ddos_guard": "ddos-guard" in body.lower() or "ddos-guard" in headers.get("server", "").lower(),
        "cloudflare": bool(headers.get("cf-ray")) or "cloudflare" in body.lower(),
        "turnstile": "turnstile" in body.lower() or "cf-turnstile" in body.lower(),
        "js_challenge": (
            "__cf_chl" in body
            or "cf_chl_prog" in body
            or "challenge-platform" in body
            or "jschl_vc" in body
        ),
        "real_html": len(body) > 2000 and "kwork" in body.lower(),
        "project_cards_hint": "projects" in body.lower() and ("want" in body.lower() or "проект" in body.lower()),
        "body_snippet": body[:1500],
    }
    return result


def probe_direct(url: str, label: str) -> dict:
    print(f"\n[httpx DIRECT] {label} -> {url}")
    try:
        with httpx.Client(
            headers=HEADERS,
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            resp = client.get(url)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {"error": str(exc), "url": url, "mode": "direct"}

    info = detect_antibot(resp)
    info["url"] = url
    info["mode"] = "direct"
    print(f"  status={info['status']}  CF={info['cloudflare']}  CF-RAY={info['cf_ray']!r}")
    print(f"  server={info['server']!r}  ddos_guard={info['ddos_guard']}  turnstile={info['turnstile']}")
    print(f"  js_challenge={info['js_challenge']}  real_html={info['real_html']}  projects={info['project_cards_hint']}")
    return info


def probe_proxy(url: str, proxy_url: str, label: str) -> dict:
    print(f"\n[httpx PROXY] {label} -> {url}")
    try:
        with httpx.Client(
            proxy=proxy_url,
            headers=HEADERS,
            follow_redirects=True,
            timeout=25.0,
        ) as client:
            resp = client.get(url)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {"error": str(exc), "url": url, "mode": "proxy", "proxy": proxy_url.split("@")[-1]}

    info = detect_antibot(resp)
    info["url"] = url
    info["mode"] = "proxy"
    info["proxy_host"] = proxy_url.split("@")[-1]
    print(f"  status={info['status']}  CF={info['cloudflare']}  CF-RAY={info['cf_ray']!r}")
    print(f"  server={info['server']!r}  ddos_guard={info['ddos_guard']}  turnstile={info['turnstile']}")
    print(f"  js_challenge={info['js_challenge']}  real_html={info['real_html']}  projects={info['project_cards_hint']}")
    return info


if __name__ == "__main__":
    results = []

    # (a) Direct
    r1 = probe_direct(TARGET_URL, "projects listing")
    results.append(r1)
    (SAMPLES_DIR / "direct_projects.txt").write_text(r1.get("body_snippet", ""), encoding="utf-8")

    # Also probe robots.txt direct (cheap check)
    r_robots = probe_direct("https://kwork.ru/robots.txt", "robots.txt")
    results.append(r_robots)
    (SAMPLES_DIR / "direct_robots.txt").write_text(r_robots.get("body_snippet", ""), encoding="utf-8")

    # (b) Proxy — use first 3 ports
    proxies = load_proxies()
    print(f"\nLoaded {len(proxies)} proxy entries")
    if proxies:
        for i, proxy_url in enumerate(proxies[:3]):
            r_proxy = probe_proxy(TARGET_URL, proxy_url, f"projects via proxy[{i}]")
            results.append(r_proxy)
            time.sleep(0.5)
    else:
        print("No proxies loaded — skipping proxy tests")

    # Save evidence
    evidence_path = SAMPLES_DIR / "httpx_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved: {evidence_path}")

    # Summary
    print("\n=== SUMMARY ===")
    for r in results:
        if "error" in r:
            print(f"  {r['mode']:10s}  ERROR: {r['error'][:80]}")
        else:
            status = r.get("status")
            cf = r.get("cloudflare")
            ddos = r.get("ddos_guard")
            jsc = r.get("js_challenge")
            real = r.get("real_html")
            print(
                f"  {r['mode']:10s}  HTTP {status}  CF={cf}  DDoS-Guard={ddos}  "
                f"JS-challenge={jsc}  real_html={real}"
            )
