"""Estimate total traffic reduction from the measured per-domain bytes,
weighted by REAL visit counts from data_750m/research_final."""
from __future__ import annotations
import json
from pathlib import Path

R = Path(__file__).resolve().parent / "exp_results.json"
data = json.loads(R.read_text(encoding="utf-8"))

# Measured wire bytes per domain (avg of samples where method ok). Fall back gracefully.
def avg(domain, method, key="wire_bytes"):
    vals = [r[method][key] for r in data if r["domain"] == domain
            and r[method].get("ok") and r[method].get(key)]
    return sum(vals) / len(vals) if vals else None

DOMAINS = ["t.me", "vk.com", "instagram.com", "2gis.ru", "zoon.ru", "spb.hh.ru",
           "prodoctorov.ru", "rusprofile.ru", "rubrikator.org", "orgzz.ru", "spb.spravker.ru"]

# Real visit counts (research_final, 132 orgs) — from analyze_traffic.py output.
VISITS = {
    "vk.com": 147, "instagram.com": 61, "t.me": 51, "2gis.ru": 47, "zoon.ru": 34,
    "spb.hh.ru": 30, "prodoctorov.ru": 13, "rubrikator.org": 12, "hh.ru": 10,
    "rusprofile.ru": 9, "orgzz.ru": 7, "spb.spravker.ru": 6,
}

# Strategy per domain: "httpx" (replace browser), "block" (browser+resource-block),
# "browser" (keep full browser — SPA/wall, no safe block).
STRATEGY = {
    "t.me": "httpx", "zoon.ru": "httpx", "spb.hh.ru": "httpx", "hh.ru": "httpx",
    "prodoctorov.ru": "httpx", "rusprofile.ru": "httpx", "rubrikator.org": "httpx",
    "orgzz.ru": "httpx", "spb.spravker.ru": "httpx",
    "2gis.ru": "block",          # SPA but resource-block still cuts a lot, content ok
    "vk.com": "httpx_cheap",     # fetch cheap via m.vk.com; extraction needs adapter
    "instagram.com": "stub",     # login-wall: don't render, take handle from snippet
}

print(f"{'domain':16}{'visits':>7}{'full_KB':>9}{'block_KB':>9}{'httpx_KB':>9}  strategy")
tot_now = tot_new = 0.0
for d in DOMAINS:
    vis = VISITS.get(d, 0)
    full = avg(d, "browser_full")
    block = avg(d, "browser_block")
    hx = avg(d, "httpx")
    strat = STRATEGY.get(d, "browser")
    now = (full or 0) * vis
    if strat == "httpx" and hx:
        new = hx * vis
    elif strat == "httpx_cheap" and hx:
        new = hx * vis
    elif strat == "block" and block:
        new = block * vis
    elif strat == "stub":
        new = 2000 * vis  # ~2KB stub, no render
    else:
        new = now
    tot_now += now
    tot_new += new
    fk = f"{full/1024:.0f}" if full else "-"
    bk = f"{block/1024:.0f}" if block else "-"
    hk = f"{hx/1024:.0f}" if hx else "-"
    print(f"{d:16}{vis:>7}{fk:>9}{bk:>9}{hk:>9}  {strat}")

print(f"\nModeled top-domain traffic NOW  : {tot_now/1024/1024:.1f} MB (over {sum(VISITS.values())} visits)")
print(f"Modeled top-domain traffic NEW  : {tot_new/1024/1024:.1f} MB")
print(f"Reduction on modeled domains    : {100*(1-tot_new/tot_now):.0f}%")
