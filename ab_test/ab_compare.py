"""Парное сравнение A/B: results_A vs results_B по каждой орг.

Метрики: насыщенность полей (особенно social/problems_signals/what_they_do),
включил ли B prefill-соцсети, и экономия поиска (serp/scrape/turns/elapsed).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ["what_they_do", "scale_indicators", "vacancies", "social", "phones",
          "emails", "websites", "problems_signals", "sources"]


def rich(card):
    card = card or {}
    c = card.get("contacts") or {}
    soc = card.get("social") or {}
    return {
        "what_they_do": 1 if (card.get("what_they_do") or "").strip() else 0,
        "scale_indicators": len(card.get("scale_indicators") or []),
        "vacancies": len(card.get("vacancies") or []),
        "social": sum(len(v) for v in soc.values() if isinstance(v, list)),
        "phones": len(c.get("phones") or []),
        "emails": len(c.get("emails") or []),
        "websites": len(c.get("websites") or []),
        "problems_signals": len(card.get("problems_signals") or []),
        "sources": len(card.get("sources") or []),
    }


def load(arm, oid):
    p = HERE / f"results_{arm}" / f"{oid}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def card_of(r):
    return (r.get("result") or {}).get("structured_output") if r else None


def stats_of(r):
    return (r.get("result") or {}).get("stats") or {} if r else {}


def main():
    sel = json.load((HERE / "ab_orgs.json").open(encoding="utf-8"))
    rows = []
    for oid in sel["oids"]:
        ra, rb = load("A", oid), load("B", oid)
        if not ra or not rb:
            continue
        ca, cb = card_of(ra), card_of(rb)
        ctxp = HERE / "context" / f"{oid}.json"
        ctx_social = 0
        if ctxp.exists():
            ctx_social = len(json.loads(ctxp.read_text(encoding="utf-8"))["card"].get("social_links") or [])
        rows.append({
            "oid": oid, "A": rich(ca), "B": rich(cb),
            "A_none": ca is None, "B_none": cb is None,
            "A_stats": stats_of(ra), "B_stats": stats_of(rb),
            "ctx_social": ctx_social,
        })

    n = len(rows)
    print(f"Пар A/B: {n}\n")
    # парные победы по полям
    print(f"{'поле':18} {'sumA':>5} {'sumB':>5}  {'B>A':>4} {'B<A':>4} {'B=A':>4}")
    for f in FIELDS:
        sa = sum(r["A"][f] for r in rows); sb = sum(r["B"][f] for r in rows)
        bw = sum(1 for r in rows if r["B"][f] > r["A"][f])
        bl = sum(1 for r in rows if r["B"][f] < r["A"][f])
        eq = n - bw - bl
        flag = " <--B лучше" if sb > sa else (" <--B хуже" if sb < sa else "")
        print(f"{f:18} {sa:>5} {sb:>5}  {bw:>4} {bl:>4} {eq:>4}{flag}")

    # экономия поиска / стоимость
    def avg(arm, key):
        xs = []
        for r in rows:
            tc = r[f"{arm}_stats"].get("tool_calls") or {}
            if key in ("serp", "scrape"):
                xs.append(tc.get("web_serp" if key == "serp" else "web_scrape", 0))
            else:
                xs.append(r[f"{arm}_stats"].get(key, 0))
        return round(statistics.mean(xs), 1) if xs else 0
    print(f"\nСтоимость (ср.): A serp={avg('A','serp')} scrape={avg('A','scrape')} "
          f"turns={avg('A','turns')} elapsed={avg('A','elapsed_seconds')}")
    print(f"               B serp={avg('B','serp')} scrape={avg('B','scrape')} "
          f"turns={avg('B','turns')} elapsed={avg('B','elapsed_seconds')}")

    # включил ли B prefill-соцсети
    b_has_ge_ctx = sum(1 for r in rows if r["ctx_social"] > 0 and r["B"]["social"] >= r["ctx_social"])
    ctx_avail = sum(1 for r in rows if r["ctx_social"] > 0)
    print(f"\nB включил >= prefill-соцсетей: {b_has_ge_ctx}/{ctx_avail} (где контекст дал соцсети)")
    none = sum(1 for r in rows if r["B_none"]), sum(1 for r in rows if r["A_none"])
    print(f"Пустых карт: A={none[1]} B={none[0]}")

    json.dump(rows, (HERE / "ab_comparison.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[+] {HERE/'ab_comparison.json'}")


if __name__ == "__main__":
    main()
