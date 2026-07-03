"""
fl_profiles_benchmark.py — benchmark top fl.ru freelancers (Ivan's etalon set).

Reads samples/<dir>/all_freelancers.jsonl (from fl_freelancers_scrape.py), picks the
top PRO/named freelancers by reviews across Ivan's niche, fetches each profile, and
extracts positioning: headline (<title>), declared specializations, hourly/monthly
rate. Analog of kwork_profiles_scrape.py. httpx-direct, no proxy.

Run from repo root:
  uv run python experiment_monitoring/experiment-fl/fl_profiles_benchmark.py --top 15
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _clean(s: str) -> str:
    import html as h
    return h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def _rub(after: str) -> int | None:
    m = re.search(r"([\d\s]+)(?:&#8381;|₽)", after)
    if not m:
        return None
    d = re.sub(r"\D", "", m.group(1))
    return int(d) if d else None


def fetch_profile(login: str) -> dict | None:
    url = f"https://www.fl.ru/users/{login}/"
    try:
        r = httpx.get(url, headers=HEADERS, timeout=35, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  profile fail {login}: {exc}")
        return None
    h = r.text
    title = re.search(r"<title>([^<]+)</title>", h)
    headline = _clean(title.group(1)) if title else None
    # declared specializations
    specs = []
    for m in re.finditer(r'data-id="category-spec"[^>]*>(.*?)</a>', h, re.S):
        t = _clean(m.group(1))
        if t:
            specs.append(t)
    hourly = monthly = None
    i = h.find("Стоимость часа работы")
    if i != -1:
        hourly = _rub(h[i:i + 120])
    j = h.find("Стоимость месяца работы")
    if j != -1:
        monthly = _rub(h[j:j + 120])
    return {"login": login, "headline": headline,
            "specializations": specs[:8], "hourly_rate": hourly, "monthly_rate": monthly}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="freelancers")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    base = HERE / "samples" / args.dir

    rows = [json.loads(l) for l in (base / "all_freelancers.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    # top PRO/named by reviews, dedup by uid
    seen: set = set()
    ranked = sorted((r for r in rows if r.get("login") and r.get("is_pro")),
                    key=lambda r: int(r.get("reviews") or 0), reverse=True)
    picks = []
    for r in ranked:
        if r["uid"] in seen:
            continue
        seen.add(r["uid"])
        picks.append(r)
        if len(picks) >= args.top:
            break

    out = []
    for r in picks:
        time.sleep(1.0 + random.uniform(0, 0.6))
        p = fetch_profile(r["login"])
        if not p:
            continue
        p.update({"name": r.get("name"), "reviews": r.get("reviews"),
                  "deals": r.get("deals"), "portfolio_works": r.get("portfolio_works"),
                  "experience_years": r.get("experience_years"),
                  "profession": r.get("profession"), "spec_text": r.get("spec_text")})
        out.append(p)
        print(f"  {r.get('name')}: {r.get('reviews')} rev, hourly {p['hourly_rate']}₽ — {p['headline']}")

    (base / "profiles_benchmark.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in out), encoding="utf-8")

    print("\n=== BENCHMARK (top PRO by reviews) ===")
    print(f"{'name':22s} {'rev':>4} {'deal':>4} {'pf':>4} {'exp':>3} {'hourly':>7} {'monthly':>8}  headline")
    for p in out:
        print(f"{(p.get('name') or '')[:22]:22s} {p.get('reviews') or 0:>4} "
              f"{p.get('deals') or 0:>4} {p.get('portfolio_works') or 0:>4} "
              f"{p.get('experience_years') or 0:>3} {str(p.get('hourly_rate') or '-'):>7} "
              f"{str(p.get('monthly_rate') or '-'):>8}  {(p.get('headline') or '')[:70]}")
    print(f"\nSaved -> {base/'profiles_benchmark.jsonl'}")


if __name__ == "__main__":
    main()
