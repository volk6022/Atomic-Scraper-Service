"""Aggregate real visited_urls + source domains across the 132-org final run.

We don't trust PLAN.md numbers blindly — recompute from data_750m/research_final.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent / "yandex_enrichment_experiment" / "data_750m"

def domain(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return "?"
    if net.startswith("www."):
        net = net[4:]
    if net.startswith("m."):
        net = net[2:]
    return net


def analyze(folder: Path):
    visited_dom = Counter()        # domains the agent actually scraped (web_scrape)
    visited_per_org = defaultdict(set)
    source_dom = Counter()         # domains cited as sources in structured_output
    n_orgs = 0
    n_visits = 0
    visits_per_org = []
    tool_calls_total = Counter()
    for f in sorted(folder.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        n_orgs += 1
        res = d.get("result", {}) or {}
        trace = res.get("trace_summary", {}) or {}
        visited = trace.get("visited_urls", []) or []
        visits_per_org.append(len(visited))
        for u in visited:
            url = u if isinstance(u, str) else (u.get("url") if isinstance(u, dict) else None)
            if not url:
                continue
            dm = domain(url)
            visited_dom[dm] += 1
            visited_per_org[dm].add(d.get("oid"))
            n_visits += 1
        # sources
        so = res.get("structured_output", {}) or {}
        for s in (so.get("sources", []) or []):
            url = s.get("url") if isinstance(s, dict) else None
            if url and url not in ("user_input",):
                source_dom[domain(url)] += 1
        # tool call stats
        stats = res.get("stats", {}) or {}
        for k, v in (stats.get("tool_calls", {}) or {}).items():
            tool_calls_total[k] += v
    return {
        "n_orgs": n_orgs,
        "n_visits": n_visits,
        "visited_dom": visited_dom,
        "visited_per_org": {k: len(v) for k, v in visited_per_org.items()},
        "source_dom": source_dom,
        "visits_per_org": visits_per_org,
        "tool_calls_total": tool_calls_total,
    }


def main():
    for name in ["research_final", "research", "research_d_q8", "research_ac"]:
        folder = BASE / name
        if not folder.exists():
            continue
        r = analyze(folder)
        if r["n_orgs"] == 0:
            continue
        print(f"\n{'='*70}\nFOLDER: {name}  orgs={r['n_orgs']}  total_visits={r['n_visits']}  "
              f"avg_visits/org={sum(r['visits_per_org'])/max(r['n_orgs'],1):.1f}")
        print(f"tool_calls: {dict(r['tool_calls_total'])}")
        print(f"\n  TOP VISITED DOMAINS (web_scrape):")
        print(f"  {'domain':28} {'visits':>6} {'orgs':>5} {'src_as_source':>13}")
        for dm, cnt in r["visited_dom"].most_common(30):
            orgs = r["visited_per_org"].get(dm, 0)
            src = r["source_dom"].get(dm, 0)
            print(f"  {dm:28} {cnt:>6} {orgs:>5} {src:>13}")
        print(f"\n  TOP SOURCE DOMAINS (cited, no scrape needed if >visits):")
        for dm, cnt in r["source_dom"].most_common(15):
            v = r["visited_dom"].get(dm, 0)
            print(f"  {dm:28} cited={cnt:>4} visited={v:>4}")


if __name__ == "__main__":
    main()
