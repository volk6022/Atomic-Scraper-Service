"""Live llama context monitor — no restart needed.

Parses the llama-server error log for per-request `slot release ... n_tokens = N`
(full active context) and `prompt eval ... / M tokens` (new tokens prefilled), and
pulls /metrics for live throughput. Appends a rolling summary every INTERVAL seconds.

Run:  uv run python yandex_enrichment_experiment/monitor_llama_ctx.py
Watch: tail -f yandex_enrichment_experiment/llama_ctx_monitor.log
"""
from __future__ import annotations
import re, time, urllib.request, statistics as st
from collections import deque

ELOG = r"C:/Users/bhunp/.pm2/logs/llama-server-error.log"
OUT = "yandex_enrichment_experiment/llama_ctx_monitor.log"
METRICS = "http://localhost:20022/metrics"
INTERVAL = 60
WINDOW = 400  # rolling window of recent requests

REL = re.compile(r"release:.*n_tokens = (\d+)")
PE = re.compile(r"prompt eval time =.*?/\s+(\d+) tokens")

ctx = deque(maxlen=WINDOW)
pre = deque(maxlen=WINDOW)
ctx_all: list[int] = []


def metric(text: str, name: str):
    # match the value line (^llamacpp:name VALUE), not the `# HELP/# TYPE` comments
    m = re.search(rf"^llamacpp:{re.escape(name)} ([\d.eE+-]+)", text, re.M)
    return m.group(1) if m else "?"


def summarize() -> str:
    if not ctx:
        return time.strftime("%H:%M:%S") + " (no requests yet)"
    c = sorted(ctx)
    p90 = c[min(len(c) - 1, int(len(c) * 0.9))]
    reuse = 100 - 100 * st.mean(pre) / st.mean(ctx) if ctx and pre else 0
    try:
        mt = urllib.request.urlopen(METRICS, timeout=4).read().decode()
        busy = metric(mt, "requests_processing")
        dtps = metric(mt, "predicted_tokens_seconds")
        nmax = metric(mt, "n_tokens_max")
    except Exception:
        busy = dtps = nmax = "?"
    cum = f"cum_n={len(ctx_all)} cum_mean={st.mean(ctx_all):.0f}" if ctx_all else ""
    return (f"{time.strftime('%H:%M:%S')} ctx(last{len(c)}): med={st.median(c):.0f} "
            f"mean={st.mean(c):.0f} p90={p90} max={max(c)} | prefill_med={st.median(pre):.0f} "
            f"reuse={reuse:.0f}% | busy={busy} decode_tps={dtps} n_tokens_max={nmax} | {cum}")


def main():
    # prime windows from existing log, then tail forward
    offset = 0
    with open(ELOG, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = REL.search(line)
            if m:
                v = int(m.group(1)); ctx.append(v); ctx_all.append(v)
            m2 = PE.search(line)
            if m2:
                pre.append(int(m2.group(1)))
        offset = f.tell()
    with open(OUT, "a", encoding="utf-8") as out:
        out.write("\n=== monitor start " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
        out.write(summarize() + "\n"); out.flush()
        while True:
            time.sleep(INTERVAL)
            with open(ELOG, encoding="utf-8", errors="ignore") as f:
                f.seek(offset)
                chunk = f.read()
                offset = f.tell()
            for line in chunk.splitlines():
                m = REL.search(line)
                if m:
                    v = int(m.group(1)); ctx.append(v); ctx_all.append(v)
                m2 = PE.search(line)
                if m2:
                    pre.append(int(m2.group(1)))
            out.write(summarize() + "\n"); out.flush()


if __name__ == "__main__":
    main()
