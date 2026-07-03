"""
fl_services_recon.py — Phase 0 recon for fl.ru SUPPLY side (freelancer catalog).

fl.ru is a project-bidding marketplace (no fixed-gig catalog like Kwork). The
supply/competition analog is the FREELANCER CATALOG: who competes in a niche,
their declared rate, rating, reviews, PRO status, specialization string.

This script probes candidate URLs and dumps structure so we can design the
scraper. httpx-direct (DDoS-Guard is passive per auto-research-fl.md). No proxy.

Run from repo root:
  uv run python experiment_monitoring/experiment-fl/fl_services_recon.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
OUT = HERE / "samples"
OUT.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Candidate supply-side URLs to probe.
CANDIDATES = [
    ("freelancers_root", "https://www.fl.ru/freelancers/"),
    ("freelancers_prog", "https://www.fl.ru/freelancers/programmirovanie/"),
    ("freelancers_python", "https://www.fl.ru/freelancers/programmirovanie/python/"),
    ("freelancers_ai", "https://www.fl.ru/freelancers/ai-iskusstvenniy-intellekt/"),
    ("freelancers_cat_prog", "https://www.fl.ru/freelancers/category/programmirovanie/"),
    ("services_root", "https://www.fl.ru/services/"),
    ("uslugi_root", "https://www.fl.ru/uslugi/"),
    ("prof_groups", "https://www.fl.ru/prof_groups/"),
]


def probe(name: str, url: str) -> dict:
    info: dict = {"name": name, "url": url}
    try:
        r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        info["error"] = repr(exc)
        return info
    info["status"] = r.status_code
    info["final_url"] = str(r.url)
    info["server"] = r.headers.get("server")
    info["ctype"] = r.headers.get("content-type")
    info["len"] = len(r.text)
    html = r.text
    # heuristic markers
    info["has_uid_meta"] = bool(re.search(r'name="current-uid"', html))
    m = re.search(r'name="current-uid"\s+content="(\d+)"', html)
    info["uid"] = m.group(1) if m else None
    # freelancer profile links: /users/<login>/ or /freelancers/<login>/
    users = re.findall(r'/users/([A-Za-z0-9_\-.]+)/', html)
    frl = re.findall(r'href="/freelancers/([A-Za-z0-9_\-.]+)/"', html)
    info["users_links"] = len(set(users))
    info["users_sample"] = sorted(set(users))[:8]
    info["freelancer_login_links"] = len(set(frl))
    # rate / price markers
    info["has_rub"] = html.count("₽")
    info["has_chas"] = html.count("час")  # "стоимость часа"
    info["has_rating"] = len(re.findall(r'rating', html, re.I))
    # class markers that might be freelancer cards
    for cls in ["b-post", "b-freelancer", "b-user", "freelancer", "b-catalog",
                "b-page__list", "card", "user-card", "b-profile"]:
        info[f"cls_{cls}"] = html.count(cls)
    # save first page HTML for the promising ones
    if r.status_code == 200 and len(html) > 5000:
        (OUT / f"recon_{name}.html").write_text(html, encoding="utf-8")
    return info


def main() -> None:
    import json
    results = []
    for name, url in CANDIDATES:
        info = probe(name, url)
        results.append(info)
        print(f"\n=== {name} -> {info.get('status')} {info.get('final_url')}")
        for k in ("server", "len", "uid", "users_links", "users_sample",
                  "freelancer_login_links", "has_rub", "has_chas"):
            print(f"    {k}: {info.get(k)}")
        # print class markers that fired
        cls_hits = {k: v for k, v in info.items() if k.startswith("cls_") and v}
        print(f"    class-markers: {cls_hits}")
    (OUT / "recon_supply_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved -> {OUT/'recon_supply_results.json'}")


if __name__ == "__main__":
    main()
