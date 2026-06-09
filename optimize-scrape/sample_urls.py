"""Pull real example visited URLs per top domain from the final run."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent / "yandex_enrichment_experiment" / "data_750m" / "research_final"

def dom(url):
    n = urlparse(url).netloc.lower()
    for p in ("www.", "m."):
        if n.startswith(p):
            n = n[len(p):]
    return n

TARGETS = {"vk.com","instagram.com","t.me","2gis.ru","zoon.ru","spb.hh.ru","hh.ru",
           "prodoctorov.ru","rusprofile.ru","rubrikator.org","orgzz.ru","spb.spravker.ru"}

by_dom = defaultdict(list)
for f in BASE.glob("*.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    trace = (d.get("result") or {}).get("trace_summary") or {}
    for u in (trace.get("visited_urls") or []):
        url = u if isinstance(u, str) else (u.get("url") if isinstance(u, dict) else None)
        if not url:
            continue
        dd = dom(url)
        if dd in TARGETS and url not in by_dom[dd]:
            by_dom[dd].append(url)

for dd in sorted(by_dom):
    print(f"\n### {dd}  ({len(by_dom[dd])} unique)")
    for url in by_dom[dd][:5]:
        print(f"  {url}")
