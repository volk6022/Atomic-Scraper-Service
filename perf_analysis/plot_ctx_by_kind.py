"""Context distributions per LLM call kind, from card perf telemetry.

For every research dir passed (default: all three 2026-06-10 zones), collects
stats.perf.llm_calls and renders, per call kind (main / critic / refraser /
compact / forced_submit):
  - histogram of prompt tokens (context)
  - histogram of completion tokens
  - context vs turn scatter for main calls (context growth over the agent loop)
plus a percentile table to stdout. This is the input for deciding whether
ctx-targeted work (batching small calls, np raise via ctx discipline) can pay.

Run: uv run python perf_analysis/plot_ctx_by_kind.py [research_dir ...]
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DEFAULT_DIRS = [
    "yandex_enrichment_experiment/data_2026-06-10_optikov/research",
    "yandex_enrichment_experiment/data_2026-06-10_petrogradka/research",
    "yandex_enrichment_experiment/data_2026-06-10_kirovsky/research",
]
OUTDIR = Path("perf_analysis/results/ctx_plots")


def q(arr: list, p: float):
    a = sorted(arr)
    return a[min(len(a) - 1, int(len(a) * p))] if a else None


def main() -> None:
    dirs = [Path(d) for d in (sys.argv[1:] or DEFAULT_DIRS)]
    calls_by_kind: dict[str, list[dict]] = defaultdict(list)
    n_cards = 0
    for d in dirs:
        for f in d.glob("*.json"):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            perf = (((j.get("result") or {}).get("stats") or {}).get("perf"))
            if not perf:
                continue
            n_cards += 1
            for c in perf.get("llm_calls") or []:
                if not c.get("error"):
                    calls_by_kind[c["kind"]].append(c)
    if not calls_by_kind:
        print("no telemetry found")
        return
    print(f"cards with telemetry: {n_cards}")
    print(f"{'kind':16s} {'n':>5s} {'ctx p50/p90/p99/max':>26s} {'compl p50/p90/p99':>20s} {'wall_s p50/p90':>14s}")
    for k, calls in sorted(calls_by_kind.items(), key=lambda kv: -len(kv[1])):
        cx = [c.get("prompt") or 0 for c in calls]
        cm = [c.get("completion") or 0 for c in calls]
        w = [c["s"] for c in calls]
        print(f"{k:16s} {len(calls):5d} "
              f"{q(cx,.5):>7}/{q(cx,.9):>6}/{q(cx,.99):>6}/{max(cx):>6} "
              f"{q(cm,.5):>7}/{q(cm,.9):>5}/{q(cm,.99):>5} "
              f"{q(w,.5):>7.1f}/{q(w,.9):>5.1f}")

    kinds = sorted(calls_by_kind, key=lambda k: -len(calls_by_kind[k]))
    fig, axes = plt.subplots(len(kinds), 2, figsize=(13, 3.2 * len(kinds)), squeeze=False)
    for i, k in enumerate(kinds):
        cx = [c.get("prompt") or 0 for c in calls_by_kind[k]]
        cm = [c.get("completion") or 0 for c in calls_by_kind[k]]
        axes[i][0].hist(cx, bins=40, color="steelblue")
        axes[i][0].set_title(f"{k}: prompt tokens (context), n={len(cx)}", fontsize=10)
        axes[i][1].hist(cm, bins=40, color="darkorange")
        axes[i][1].set_title(f"{k}: completion tokens", fontsize=10)
        for ax in axes[i]:
            ax.grid(alpha=0.3)
    fig.tight_layout()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out1 = OUTDIR / "ctx_hist_by_kind.png"
    fig.savefig(out1, dpi=110)

    main_calls = [c for c in calls_by_kind.get("main", []) if isinstance(c.get("turn"), int)]
    if main_calls:
        fig2, ax = plt.subplots(figsize=(10, 6))
        ax.scatter([c["turn"] for c in main_calls],
                   [c.get("prompt") or 0 for c in main_calls], s=8, alpha=0.35)
        ax.set_xlabel("turn")
        ax.set_ylabel("prompt tokens (context)")
        ax.set_title(f"main calls: context growth over the agent loop (n={len(main_calls)})")
        ax.grid(alpha=0.3)
        out2 = OUTDIR / "ctx_vs_turn_main.png"
        fig2.savefig(out2, dpi=110)
        print(f"plots -> {out1}, {out2}")
    else:
        print(f"plots -> {out1}")


if __name__ == "__main__":
    main()
