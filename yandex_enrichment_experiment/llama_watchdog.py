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

Second trigger (added after the 2026-06-12 16:20 episode): a full wedge.
There requests never COMPLETE (clients cancel at their timeout), so no eval
samples arrive and the tps check never fires. Signature: /health answers 200
while /metrics hangs (server loop starved). Root cause found that day: WDDM
demoted part of llama's CUDA allocations to shared sysmem (dwm/desktop apps
competing for VRAM) → decode reads pages over PCIe, cuda engine ~99% busy,
VRAM bus ~0%. The snapshot therefore also captures per-process GPU engine
usage and local/shared GPU memory.

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
import urllib.error
import urllib.request
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

BASE_URL = "http://localhost:20022"
PROBE_TIMEOUT_S = 6.0
WEDGE_PROBES = 2       # consecutive (health ok, metrics hang) checks before restart

EV = re.compile(r"\|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
CANCEL = re.compile(r"stop: cancel task")

samples: deque[tuple[float, float, int]] = deque()  # (arrival_ts, eval_ms, tokens)


def log(msg: str) -> None:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


_PS_GPU_BREAKDOWN = (
    "$e = Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue; "
    "$e.CounterSamples | Where-Object CookedValue -gt 0.5 | Sort-Object CookedValue -Descending | "
    "Select-Object -First 10 | ForEach-Object { '{0,6:N1}%  {1}' -f $_.CookedValue, $_.InstanceName }; "
    "$m = Get-Counter '\\GPU Process Memory(*)\\Local Usage','\\GPU Process Memory(*)\\Shared Usage' "
    "-ErrorAction SilentlyContinue; "
    "$m.CounterSamples | Where-Object CookedValue -gt 100MB | ForEach-Object { "
    "'{0,6:N0}MB  {1}' -f ($_.CookedValue/1MB), $_.Path }"
)


def snapshot_gpu(tag: str) -> None:
    blocks = [f"=== {tag} {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ==="]
    for args in (
        ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,"
         "memory.total,clocks.sm,clocks.mem,power.draw,pstate,temperature.gpu",
         "--format=csv"],
        ["nvidia-smi", "-q", "-d", "PERFORMANCE"],
        # per-process engine usage + local/shared GPU memory: the WDDM-demotion
        # evidence (shared usage on the llama pid = pages evicted to sysmem)
        ["powershell", "-NoProfile", "-Command", _PS_GPU_BREAKDOWN],
    ):
        try:
            blocks.append(subprocess.run(args, capture_output=True, text=True,
                                         timeout=30).stdout)
        except Exception as e:  # noqa: BLE001
            blocks.append(f"({args[0]} failed: {e})")
    with open(SNAP, "a", encoding="utf-8") as f:
        f.write("\n".join(blocks) + "\n")


def _http_ok(path: str) -> bool:
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=PROBE_TIMEOUT_S) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 (timeout, conn refused, 503 while loading)
        return False


def probe_wedge() -> bool:
    """True = server is up (health ok) but its loop is starved (metrics hangs)."""
    return _http_ok("/health") and not _http_ok("/metrics")


def restart_llama() -> None:
    # pm2 on Windows can fail to kill a wedged instance and spawn a new one
    # NEXT to it (2026-06-12: three llama-server.exe fighting for 8GB VRAM,
    # every fresh instance born straight into WDDM demotion). Kill them all
    # first, then let pm2 bring up exactly one.
    try:
        subprocess.run("taskkill /IM llama-server.exe /F", shell=True,
                       capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        log(f"taskkill failed: {e}")
    try:
        r = subprocess.run("pm2 restart llama-server", shell=True,
                           capture_output=True, text=True, timeout=120)
        log(f"pm2 restart rc={r.returncode}")
    except Exception as e:  # noqa: BLE001
        log(f"pm2 restart FAILED: {e}")


def main() -> None:
    log(f"watchdog start (threshold={TPS_THRESHOLD} tps, window={WINDOW_S:.0f}s, "
        f"min_n={MIN_REQUESTS}, wedge_probes={WEDGE_PROBES})")
    with open(ELOG, encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)
        offset = f.tell()
    wedge_streak = 0
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
        cancels = 0
        for line in chunk.splitlines():
            m = EV.search(line)
            if m:
                samples.append((now, float(m.group(1)), int(m.group(2))))
            elif CANCEL.search(line):
                cancels += 1
        while samples and samples[0][0] < now - WINDOW_S:
            samples.popleft()

        # Wedge path: no evals ever complete, so the tps check below is blind.
        if probe_wedge():
            wedge_streak += 1
            log(f"WEDGE PROBE: /health ok, /metrics hung "
                f"({wedge_streak}/{WEDGE_PROBES}, cancels_last_min={cancels})")
            if wedge_streak >= WEDGE_PROBES:
                log("WEDGE: server loop starved — snapshotting GPU and restarting llama")
                snapshot_gpu(f"wedge cancels={cancels}")
                restart_llama()
                samples.clear()
                wedge_streak = 0
                time.sleep(COOLDOWN_S)
            continue
        wedge_streak = 0

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
