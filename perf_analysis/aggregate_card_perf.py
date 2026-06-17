"""Aggregate stats.perf telemetry across instrumented research cards.

Produces: time-bucket % (llm by kind / serp / scrape / proxy waste), per-call-kind
LLM context (prompt tokens) and duration distributions, serp failure stats,
scrape method/proxy stats.

Run: uv run python perf_analysis/aggregate_card_perf.py <research_dir>
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path


def q(arr: list, p: float):
    if not arr:
        return None
    a = sorted(arr)
    return a[min(len(a) - 1, int(len(a) * p))]


def main() -> None:
    d = Path(sys.argv[1] if len(sys.argv) > 1 else
             "yandex_enrichment_experiment/data_2026-06-10_optikov/research")
    cards = []
    for f in sorted(d.glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        perf = (((j.get("result") or {}).get("stats") or {}).get("perf"))
        if perf:
            cards.append((f.name, j, perf))
    print(f"instrumented cards: {len(cards)} (of {len(list(d.glob('*.json')))})\n")
    if not cards:
        return

    tot = Counter()
    llm_by_kind: dict[str, dict[str, list]] = defaultdict(lambda: {"prompt": [], "completion": [], "s": []})
    serp_walls, serp_zero = [], 0
    scrape_by_method: dict[str, list] = defaultdict(list)
    proxy_fail_ports = Counter()
    elapsed_all = 0.0

    for _, j, perf in cards:
        t = perf["totals"]
        elapsed_all += t["elapsed_s"]
        for k in ("llm_main_s", "llm_critic_s", "llm_refraser_s", "llm_compact_s",
                  "llm_forced_submit_s", "llm_failed_s", "serp_s", "scrape_s",
                  "scrape_failed_s", "scrape_proxy_waste_s", "accounted_s"):
            tot[k] += t.get(k) or 0
        for c in perf.get("llm_calls") or []:
            k = c["kind"] + ("_failed" if c.get("error") else "")
            llm_by_kind[k]["s"].append(c["s"])
            if not c.get("error"):
                llm_by_kind[k]["prompt"].append(c.get("prompt") or 0)
                llm_by_kind[k]["completion"].append(c.get("completion") or 0)
        for tc in perf.get("tool_calls") or []:
            if tc["name"] == "web_serp":
                serp_walls.append(tc["s"])
                if not tc.get("n_results"):
                    serp_zero += 1
            else:
                scrape_by_method[tc.get("method") or "?"].append(tc["s"])
                if (tc.get("proxy_waste_s") or 0) > 5:
                    for p in tc.get("proxies") or []:
                        proxy_fail_ports[p.rsplit(":", 1)[-1]] += 1

    unacc = elapsed_all - tot["accounted_s"]
    print(f"== time buckets (sum over {len(cards)} cards; total {elapsed_all/3600:.2f} h) ==")
    rows = [
        ("llm main", tot["llm_main_s"]), ("llm critic", tot["llm_critic_s"]),
        ("llm refraser", tot["llm_refraser_s"]), ("llm compact", tot["llm_compact_s"]),
        ("llm forced_submit", tot["llm_forced_submit_s"]),
        ("llm FAILED (timeout/retry)", tot["llm_failed_s"]),
        ("serp", tot["serp_s"]), ("scrape", tot["scrape_s"]),
        ("unaccounted (driver/poll)", unacc),
    ]
    for name, v in sorted(rows, key=lambda r: -r[1]):
        print(f"  {name:28s} {v/3600:6.2f} h  {100*v/elapsed_all:5.1f}%")
    print(f"  -- inside scrape: failed-attempt time {tot['scrape_failed_s']/3600:.2f} h "
          f"({100*tot['scrape_failed_s']/elapsed_all:.1f}%), of it proxy-classified "
          f"{tot['scrape_proxy_waste_s']/3600:.2f} h ({100*tot['scrape_proxy_waste_s']/elapsed_all:.1f}%)")

    print("\n== LLM per call kind: context (prompt tok) / completion / wall s ==")
    for k, v in sorted(llm_by_kind.items(), key=lambda kv: -sum(kv[1]["s"])):
        n = len(v["s"])
        print(f"  {k:16s} n={n:4d}  time={sum(v['s'])/3600:5.2f}h  "
              f"wall med={q(v['s'],.5):.0f}s p90={q(v['s'],.9):.0f}s | "
              f"ctx med={q(v['prompt'],.5) or 0:>6} p90={q(v['prompt'],.9) or 0:>6} max={max(v['prompt'] or [0]):>6} | "
              f"compl med={q(v['completion'],.5) or 0:>5} p90={q(v['completion'],.9) or 0:>5}")

    print(f"\n== serp ==  calls={len(serp_walls)} zero-result={serp_zero} "
          f"({100*serp_zero/max(1,len(serp_walls)):.0f}%) wall med={q(serp_walls,.5):.1f}s "
          f"p90={q(serp_walls,.9):.1f}s  total={sum(serp_walls)/3600:.2f}h")
    print("\n== scrape by method ==")
    for m, walls in sorted(scrape_by_method.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {m:16s} n={len(walls):4d}  med={q(walls,.5):.1f}s p90={q(walls,.9):.1f}s total={sum(walls)/3600:.2f}h")
    if proxy_fail_ports:
        print("\n== ports involved in proxy-waste scrapes (top) ==")
        print("  " + ", ".join(f"{p}:{c}" for p, c in proxy_fail_ports.most_common(15)))


if __name__ == "__main__":
    main()
