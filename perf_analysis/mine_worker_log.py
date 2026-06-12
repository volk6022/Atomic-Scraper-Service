"""Wall-time decomposition of the 2026-06-11 optikov research run from existing logs.

Approach: each taskiq worker process runs ONE research task at a time, so its
log-line stream is a per-task event timeline. Every logged event marks the END
of an activity; the gap from the previous event in the same worker is attributed
to a bucket:

  - POST .../v1/chat/completions  -> llm        (turn wall incl. queue+prefill+decode)
  - GET localhost:8080/search     -> serp       (one SearXNG attempt)
  - SearXNG ok/empty/failed       -> serp_meta  (0-length marker, same ts as GET)
  - GET <external url>            -> scrape_httpx (httpx_ssr attempt)
  - Starting site enrichment      -> dispatch   (gap after LLM/prev attempt; ~0)
  - Extracted N words / Site enrichment failed -> scrape_browser
  - scrape_url attempt failed     -> marker (browser attempt end, dup of above)
  - openai Retrying request       -> llm_retry_wait (openai client backoff)

Gaps > IDLE_GAP_S are counted as idle (worker had no task) and excluded.
Also pairs browser-enrichment episodes start->end for per-proxy-port stats.

Run: uv run python perf_analysis/mine_worker_log.py
"""
from __future__ import annotations

import json
import re
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

LOG = Path(r"C:\Users\bhunp\.pm2\logs\taskiq-worker-error.log")
OUT = Path("perf_analysis/results/worker_timeline_2026-06-11.json")
T_FROM = datetime(2026, 6, 11, 0, 0, 0)
T_TO = datetime(2026, 6, 12, 6, 0, 0)
IDLE_GAP_S = 900.0  # >15 min in one worker stream = no task assigned

LINE = re.compile(
    r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d+)\]\[([^\]]+)\]\[(\w+)\s*\]\[(worker-\d+|MainProcess)\] (.*)"
)
PORT = re.compile(r"proxy=\w+://[^:]+:(\d+)")


def classify(logger: str, msg: str) -> tuple[str, dict]:
    """-> (bucket_of_preceding_interval, extra)"""
    if logger == "httpx":
        if "POST http://localhost:20022" in msg:
            return "llm", {}
        if "GET http://localhost:8080/search" in msg:
            return "serp", {}
        m = re.search(r"(?:GET|POST) (https?://\S+)", msg)
        if m:
            return "scrape_httpx", {"url": m.group(1)}
        return "other", {}
    if logger == "openai._base_client":
        return "llm_retry_wait", {}
    if logger.endswith("searxng_client"):
        return "serp_meta", {"empty": "empty organic" in msg or "failed" in msg}
    if logger.endswith("site_enricher"):
        if msg.startswith("Starting site enrichment"):
            mp = PORT.search(msg)
            return "enrich_start", {"port": mp.group(1) if mp else "?"}
        if msg.startswith("Extracted"):
            return "scrape_browser", {"ok": True}
        if msg.startswith("Site enrichment failed"):
            kind = (
                "proxy" if any(s in msg for s in ("ERR_TIMED_OUT", "ERR_TUNNEL", "Timeout", "ERR_PROXY",
                                                  "ERR_CONNECTION", "ERR_EMPTY", "ERR_SOCKS"))
                else "other"
            )
            return "scrape_browser", {"ok": False, "fail_kind": kind}
        return "other", {}
    if logger.endswith("research.tools"):
        return "marker", {}
    if logger.endswith("research.agent"):
        return "llm", {"forced_fail": True}  # forced submit failed after waiting on llama
    return "other", {}


def main() -> None:
    buckets: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    last_ts: dict[str, datetime] = {}
    llm_walls: list[float] = []
    serp_walls: list[float] = []
    httpx_walls: list[float] = []
    browser_walls_ok: list[float] = []
    browser_walls_fail: list[float] = []
    idle_s = 0.0
    # browser episode pairing: worker -> (start_ts, port)
    open_enrich: dict[str, tuple[datetime, str]] = {}
    port_stats: dict[str, Counter] = defaultdict(Counter)
    port_time: dict[str, float] = defaultdict(float)
    serp_attempts_empty = 0
    serp_ok = 0
    window_min: datetime | None = None
    window_max: datetime | None = None

    with open(LOG, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if not (T_FROM <= ts <= T_TO):
                continue
            worker = m.group(5)
            if worker == "MainProcess":
                continue
            logger, msg = m.group(3), m.group(6)
            bucket, extra = classify(logger, msg)

            window_min = ts if window_min is None else min(window_min, ts)
            window_max = ts if window_max is None else max(window_max, ts)

            prev = last_ts.get(worker)
            gap = (ts - prev).total_seconds() if prev else 0.0
            last_ts[worker] = ts

            if bucket in ("marker", "serp_meta", "other"):
                if bucket == "serp_meta":
                    if extra.get("empty"):
                        serp_attempts_empty += 1
                    else:
                        serp_ok += 1
                # zero-length markers: don't consume the gap (leave attribution
                # to the line that follows); but to avoid double counting we DO
                # reset last_ts above. Compensate: add gap to the marker's
                # natural bucket.
                if bucket == "serp_meta":
                    buckets["serp"] += min(gap, IDLE_GAP_S) if gap < IDLE_GAP_S else 0.0
                continue

            if gap >= IDLE_GAP_S:
                idle_s += gap
                gap = 0.0

            if bucket == "enrich_start":
                buckets["dispatch"] += gap
                open_enrich[worker] = (ts, extra.get("port", "?"))
                counts["enrich_start"] += 1
                continue

            buckets[bucket] += gap
            counts[bucket] += 1

            if bucket == "llm":
                llm_walls.append(gap)
            elif bucket == "serp":
                serp_walls.append(gap)
            elif bucket == "scrape_httpx":
                httpx_walls.append(gap)
            elif bucket == "scrape_browser":
                (browser_walls_ok if extra.get("ok") else browser_walls_fail).append(gap)
                opened = open_enrich.pop(worker, None)
                if opened:
                    ep_dur = (ts - opened[0]).total_seconds()
                    if ep_dur < IDLE_GAP_S:
                        port = opened[1]
                        port_time[port] += ep_dur
                        port_stats[port]["ok" if extra.get("ok") else "fail"] += 1
                        if not extra.get("ok"):
                            port_stats[port][extra.get("fail_kind", "other")] += 1

    def pct(x: float, tot: float) -> str:
        return f"{100*x/tot:.1f}%" if tot else "?"

    active = sum(buckets.values())
    summary = {
        "window": [str(window_min), str(window_max)],
        "active_attributed_s": round(active, 0),
        "idle_excluded_s": round(idle_s, 0),
        "buckets_s": {k: round(v, 0) for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])},
        "buckets_pct_of_active": {k: pct(v, active) for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])},
        "counts": dict(counts),
        "serp": {
            "ok": serp_ok, "empty_retries": serp_attempts_empty,
            "wall_med_s": round(st.median(serp_walls), 1) if serp_walls else None,
            "wall_mean_s": round(st.mean(serp_walls), 1) if serp_walls else None,
        },
        "llm": {
            "n": len(llm_walls),
            "wall_med_s": round(st.median(llm_walls), 1) if llm_walls else None,
            "wall_mean_s": round(st.mean(llm_walls), 1) if llm_walls else None,
            "wall_p90_s": round(sorted(llm_walls)[int(len(llm_walls)*0.9)], 1) if llm_walls else None,
        },
        "scrape_browser": {
            "ok_n": len(browser_walls_ok),
            "ok_med_s": round(st.median(browser_walls_ok), 1) if browser_walls_ok else None,
            "fail_n": len(browser_walls_fail),
            "fail_med_s": round(st.median(browser_walls_fail), 1) if browser_walls_fail else None,
            "fail_time_s": round(sum(browser_walls_fail), 0),
        },
        "scrape_httpx": {
            "n": len(httpx_walls),
            "med_s": round(st.median(httpx_walls), 1) if httpx_walls else None,
        },
        "ports_top_fail": {
            p: dict(c) for p, c in sorted(port_stats.items(), key=lambda kv: -kv[1]["fail"])[:15]
        },
        "ports_time_top": {p: round(t, 0) for p, t in sorted(port_time.items(), key=lambda kv: -kv[1])[:15]},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
