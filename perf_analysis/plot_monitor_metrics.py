"""Plot the time series of every metric written by monitor_llama_ctx.py.

Parses yandex_enrichment_experiment/llama_ctx_monitor.log (one summary line per
minute, segments delimited by `=== monitor start YYYY-mm-dd HH:MM:SS ===`),
reconstructs absolute timestamps (date comes from the segment header; a
day rollover is detected when HH:MM:SS decreases), and renders one subplot per
metric into perf_analysis/results/monitor_plots/<timestamp>.png.

Run: uv run python perf_analysis/plot_monitor_metrics.py [--last-segment]
  --last-segment : plot only the most recent monitor session (default: all)

Requires matplotlib (installed into the venv via `uv pip install matplotlib`).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

LOG = Path("yandex_enrichment_experiment/llama_ctx_monitor.log")
OUTDIR = Path("perf_analysis/results/monitor_plots")

SEG = re.compile(r"=== monitor start (\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) ===")
# metrics as `name=value`; ctx aggregate fields are prefixed for uniqueness
LINE = re.compile(
    r"^(\d\d:\d\d:\d\d) ctx\(last\d+\): med=(?P<ctx_med>\d+) mean=(?P<ctx_mean>\d+) "
    r"p90=(?P<ctx_p90>\d+) max=(?P<ctx_max>\d+) \| prefill_med=(?P<prefill_med>\d+) "
    r"reuse=(?P<reuse_pct>-?\d+)%(?: \| dec_tps=(?P<dec_tps>[\d.]+|\?))? \| "
    r"busy=(?P<busy>[\d.eE+-]+|\?) decode_tps=(?P<metrics_tps>[\d.eE+-]+|\?) "
    r"n_tokens_max=(?P<n_tokens_max>[\d.eE+-]+|\?)"
)


def parse() -> list[dict]:
    rows: list[dict] = []
    seg_date: datetime | None = None
    prev_t: datetime | None = None
    for raw in LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = SEG.search(raw)
        if m:
            seg_date = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
            prev_t = None
            continue
        m = LINE.match(raw.strip())
        if not m or seg_date is None:
            continue
        hms = datetime.strptime(m.group(1), "%H:%M:%S").time()
        t = datetime.combine(seg_date.date(), hms)
        if prev_t and t < prev_t:  # crossed midnight
            seg_date += timedelta(days=1)
            t = datetime.combine(seg_date.date(), hms)
        prev_t = t
        row: dict = {"t": t, "segment": seg_date}
        for k, v in m.groupdict().items():
            if v is None or v == "?":
                row[k] = None
            else:
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = None
        rows.append(row)
    return rows


def main() -> None:
    rows = parse()
    if "--last-segment" in sys.argv and rows:
        last = rows[-1]["segment"]
        rows = [r for r in rows if r["segment"] == last]
    if not rows:
        print("no monitor data parsed")
        return
    metrics = ["ctx_med", "ctx_mean", "ctx_p90", "ctx_max", "prefill_med",
               "reuse_pct", "dec_tps", "metrics_tps", "busy", "n_tokens_max"]
    titles = {
        "ctx_med": "context per request, median (tok)",
        "ctx_mean": "context per request, mean (tok)",
        "ctx_p90": "context per request, p90 (tok)",
        "ctx_max": "context per request, max (tok)",
        "prefill_med": "new prefill per request, median (tok)",
        "reuse_pct": "KV reuse (%)",
        "dec_tps": "decode throughput, rolling (tok/s) — watchdog metric",
        "metrics_tps": "decode tps (/metrics gauge)",
        "busy": "requests processing (/metrics)",
        "n_tokens_max": "n_tokens_max (/metrics)",
    }
    ts = [r["t"] for r in rows]
    fig, axes = plt.subplots(5, 2, figsize=(16, 18), sharex=True)
    for ax, name in zip(axes.flat, metrics):
        ys = [r.get(name) for r in rows]
        ax.plot(ts, ys, lw=0.9)
        ax.set_title(titles[name], fontsize=10)
        ax.grid(alpha=0.3)
        if name == "dec_tps":
            ax.axhline(11, color="red", ls="--", lw=0.8, label="watchdog threshold")
            ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %H:%M"))
    fig.autofmt_xdate()
    fig.suptitle(f"llama monitor metrics  {ts[0]:%Y-%m-%d %H:%M} → {ts[-1]:%Y-%m-%d %H:%M}  (n={len(rows)})")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"monitor_{ts[-1]:%Y%m%d_%H%M}.png"
    fig.savefig(out, dpi=110)
    print(f"rows={len(rows)} -> {out}")


if __name__ == "__main__":
    main()
