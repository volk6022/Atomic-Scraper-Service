"""Collect up to 20 unique real URLs per target domain from ALL run folders,
so each per-site scale test hits 20 different pages (varied traffic volumes)."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[2] / "yandex_enrichment_experiment" / "data_750m"
FOLDERS = ["research_final", "research", "research_ac", "research_d_q8", "research_b_full"]

def dom(url: str) -> str:
    n = urlparse(url).netloc.lower()
    for p in ("www.", "m."):
        if n.startswith(p):
            n = n[len(p):]
    return n

# Map the netloc we see in data -> the site key we test under.
TARGETS = {
    "t.me": "t.me",
    "spb.hh.ru": "hh.ru", "hh.ru": "hh.ru",
    "prodoctorov.ru": "prodoctorov.ru",
    "rusprofile.ru": "rusprofile.ru",
    "zoon.ru": "zoon.ru",
    "rubrikator.org": "rubrikator.org",
    "orgzz.ru": "orgzz.ru",
    "spb.spravker.ru": "spravker.ru", "spravker.ru": "spravker.ru",
    "vk.com": "vk.com",
    "2gis.ru": "2gis.ru",
}

by_site = defaultdict(list)
seen = defaultdict(set)
for folder in FOLDERS:
    fdir = BASE / folder
    if not fdir.exists():
        continue
    for f in fdir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        trace = (d.get("result") or {}).get("trace_summary") or {}
        for u in (trace.get("visited_urls") or []):
            url = u if isinstance(u, str) else (u.get("url") if isinstance(u, dict) else None)
            if not url:
                continue
            site = TARGETS.get(dom(url))
            if not site:
                continue
            # normalise: strip trailing tab fragments / dup query
            key = url.split("#")[0]
            if key in seen[site]:
                continue
            seen[site].add(key)
            by_site[site].append(key)

out = {site: urls[:20] for site, urls in by_site.items()}
dest = Path(__file__).resolve().parent / "urls.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
for site, urls in sorted(out.items()):
    print(f"{site:18} {len(urls):>3} urls")
print(f"\nwrote {dest}")
