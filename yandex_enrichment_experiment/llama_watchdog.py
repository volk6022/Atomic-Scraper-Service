"""llama decode-degradation watchdog.

Known failure mode (seen 2026-06-11, also previously in LM Studio): under
sustained load decode collapses ~4-5x (8 tok/s vs 38 healthy) at identical
config — in Task Manager terms CUDA usage drops while the "3D" engine spikes;
VRAM stays flat. Root cause not yet diagnosed; until it is, the mitigation is
a server restart.

This watchdog tails the llama-server error log, keeps a rolling window of
per-request decode timings, and when throughput stays below TPS_THRESHOLD:
  1. dumps a GPU diagnostic snapshot (nvidia-smi state + throttle reasons)
     to llama_degradation_snapshots.log — the evidence for later diagnosis;
  2. `pm2 restart llama-server`;
  3. cools down while the model reloads.

Stdlib-only (runs under pm2 with the venv python, no deps).
Run:  pm2 start yandex_enrichment_experiment/llama_watchdog.py --name llama-watchdog \
          --interpreter <venv>/Scripts/python.exe
Logs: yandex_enrichment_experiment/llama_watchdog.log
"""
from __future__ import annotations

import datetime
import re
import subprocess
import time
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELOG = Path(r"C:/Users/bhunp/.pm2/logs/llama-server-error.log")
OUT = HERE / "llama_watchdog.log"
SNAP = HERE / "llama_degradation_snapshots.log"

TPS_THRESHOLD = 11.0   # rolling sum(tokens)/sum(eval_s); healthy ~37, degraded ~8
WINDOW_S = 600.0       # consider eval samples seen in the last 10 min
MIN_REQUESTS = 8       # don't judge on fewer samples (idle/llm-quiet periods)
CHECK_EVERY = 60.0
COOLDOWN_S = 900.0     # after a restart: model reload + window refill

EV = re.compile(r"\|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens")

samples: deque[tuple[float, float, int]] = deque()  # (arrival_ts, eval_ms, tokens)


def log(msg: str) -> None:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def snapshot_gpu(tag: str) -> None:
    blocks = [f"=== {tag} {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ==="]
    for args in (
        ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,"
         "memory.total,clocks.sm,clocks.mem,power.draw,pstate,temperature.gpu",
         "--format=csv"],
        ["nvidia-smi", "-q", "-d", "PERFORMANCE"],
    ):
        try:
            blocks.append(subprocess.run(args, capture_output=True, text=True,
                                         timeout=20).stdout)
        except Exception as e:  # noqa: BLE001
            blocks.append(f"({' '.join(args)} failed: {e})")
    with open(SNAP, "a", encoding="utf-8") as f:
        f.write("\n".join(blocks) + "\n")


def restart_llama() -> None:
    try:
        r = subprocess.run("pm2 restart llama-server", shell=True,
                           capture_output=True, text=True, timeout=120)
        log(f"pm2 restart rc={r.returncode}")
    except Exception as e:  # noqa: BLE001
        log(f"pm2 restart FAILED: {e}")


def main() -> None:
    log(f"watchdog start (threshold={TPS_THRESHOLD} tps, window={WINDOW_S:.0f}s, "
        f"min_n={MIN_REQUESTS})")
    with open(ELOG, encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)
        offset = f.tell()
    while True:
        time.sleep(CHECK_EVERY)
        try:
            size = ELOG.stat().st_size
            if size < offset:  # log truncated/rotated
                offset = 0
            with open(ELOG, encoding="utf-8", errors="ignore") as f:
                f.seek(offset)
                chunk = f.read()
                offset = f.tell()
        except OSError as e:
            log(f"log read failed: {e}")
            continue
        now = time.time()
        for line in chunk.splitlines():
            m = EV.search(line)
            if m:
                samples.append((now, float(m.group(1)), int(m.group(2))))
        while samples and samples[0][0] < now - WINDOW_S:
            samples.popleft()
        if len(samples) < MIN_REQUESTS:
            continue
        ms = sum(s[1] for s in samples)
        tps = sum(s[2] for s in samples) / (ms / 1000) if ms else 0.0
        log(f"dec_tps={tps:.1f} (n={len(samples)})")
        if tps < TPS_THRESHOLD:
            log(f"DEGRADATION: dec_tps={tps:.1f} < {TPS_THRESHOLD} over "
                f"{len(samples)} reqs — snapshotting GPU and restarting llama")
            snapshot_gpu(f"degradation dec_tps={tps:.1f}")
            restart_llama()
            samples.clear()
            time.sleep(COOLDOWN_S)


if __name__ == "__main__":
    main()
