"""Per-request prefill/decode stats from llama-server-error.log, per server-session.

The log has no wall timestamps; sessions are delimited by server starts. For each
session: request count, sum/median of prompt-eval ms, eval (decode) ms, total ms,
tokens prefilled vs context size (slot release n_tokens), decode tok/s.

Run: uv run python perf_analysis/mine_llama_log.py [session_index_from_end=1]
(1 = previous session — the 2026-06-11 research run if the server was restarted once after.)
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

LOG = Path(r"C:\Users\bhunp\.pm2\logs\llama-server-error.log")
OUT = Path("perf_analysis/results/llama_sessions.json")

START = re.compile(r"main: server is listening")
PE = re.compile(r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
EV = re.compile(r"\|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
TOT = re.compile(r"total time =\s*([\d.]+) ms")
REL = re.compile(r"release:.*n_tokens = (\d+)")


def main() -> None:
    sessions: list[dict] = []
    cur: dict | None = None

    def fresh() -> dict:
        return {"pe_ms": [], "pe_tok": [], "ev_ms": [], "ev_tok": [], "tot_ms": [], "ctx": []}

    cur = fresh()  # content before first marker (partial session)
    with open(LOG, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if START.search(line):
                sessions.append(cur)
                cur = fresh()
                continue
            m = PE.search(line)
            if m:
                cur["pe_ms"].append(float(m.group(1)))
                cur["pe_tok"].append(int(m.group(2)))
                continue
            m = EV.search(line)
            if m:
                cur["ev_ms"].append(float(m.group(1)))
                cur["ev_tok"].append(int(m.group(2)))
                continue
            m = TOT.search(line)
            if m:
                cur["tot_ms"].append(float(m.group(1)))
                continue
            m = REL.search(line)
            if m:
                cur["ctx"].append(int(m.group(1)))
    sessions.append(cur)

    def summarize(s: dict) -> dict | None:
        n = len(s["tot_ms"])
        if n < 5:
            return None
        pe_s = sum(s["pe_ms"]) / 1000
        ev_s = sum(s["ev_ms"]) / 1000
        tot_s = sum(s["tot_ms"]) / 1000
        ctx = sorted(s["ctx"])
        return {
            "requests": n,
            "busy_total_h": round(tot_s / 3600, 2),
            "prefill_h": round(pe_s / 3600, 2),
            "decode_h": round(ev_s / 3600, 2),
            "prefill_pct_of_busy": round(100 * pe_s / tot_s, 1) if tot_s else None,
            "decode_pct_of_busy": round(100 * ev_s / tot_s, 1) if tot_s else None,
            "req_total_med_s": round(st.median(s["tot_ms"]) / 1000, 1),
            "req_total_mean_s": round(st.mean(s["tot_ms"]) / 1000, 1),
            "req_total_p90_s": round(sorted(s["tot_ms"])[int(n * 0.9)] / 1000, 1),
            "prefill_tok_med": int(st.median(s["pe_tok"])) if s["pe_tok"] else None,
            "prefill_tok_mean": int(st.mean(s["pe_tok"])) if s["pe_tok"] else None,
            "prefill_tps": round(sum(s["pe_tok"]) / pe_s, 0) if pe_s else None,
            "decode_tok_med": int(st.median(s["ev_tok"])) if s["ev_tok"] else None,
            "decode_tok_mean": int(st.mean(s["ev_tok"])) if s["ev_tok"] else None,
            "decode_tps": round(sum(s["ev_tok"]) / ev_s, 1) if ev_s else None,
            "ctx_med": int(st.median(ctx)) if ctx else None,
            "ctx_mean": int(st.mean(ctx)) if ctx else None,
            "ctx_p90": ctx[int(len(ctx) * 0.9)] if ctx else None,
            "ctx_max": ctx[-1] if ctx else None,
        }

    out = []
    for i, s in enumerate(sessions):
        summ = summarize(s)
        if summ:
            out.append({"session_from_end": len(sessions) - 1 - i, **summ})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for rec in out[-4:]:
        print(json.dumps(rec, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
