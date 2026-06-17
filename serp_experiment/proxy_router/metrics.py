"""Metrics — JSONL events + heartbeat + /metrics snapshot."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .worker import Worker
    from .pool import WorkerPool


log = logging.getLogger(__name__)


@dataclass
class GlobalCounters:
    started_at: float = field(default_factory=time.monotonic)
    connect_main_total: int = 0
    connect_main_503: int = 0
    connect_main_502: int = 0
    connect_probe_total: int = 0
    connect_probe_502: int = 0
    probe_total: int = 0
    probe_clean: int = 0
    # для rate per minute
    connect_main_recent: deque = field(default_factory=lambda: deque(maxlen=600))
    acquire_latency_ms: deque = field(default_factory=lambda: deque(maxlen=200))

    def uptime_s(self) -> int:
        return int(time.monotonic() - self.started_at)

    def connect_rate_1m(self) -> float:
        now = time.monotonic()
        cutoff = now - 60
        n = sum(1 for ts in self.connect_main_recent if ts >= cutoff)
        return n / 60.0

    def acquire_p95_ms(self) -> int:
        if not self.acquire_latency_ms:
            return 0
        s = sorted(self.acquire_latency_ms)
        idx = max(0, int(round(0.95 * (len(s) - 1))))
        return int(s[idx])

    def probe_clean_pct(self) -> float:
        if self.probe_total == 0:
            return 0.0
        return self.probe_clean / self.probe_total


class MetricsCollector:
    """JSONL events + in-memory counters + heartbeat task."""

    def __init__(self, jsonl_path: Path, heartbeat_seconds: float = 10.0) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._jsonl_fh = self.jsonl_path.open("a", encoding="utf-8", buffering=1)  # line-buffered
        self.heartbeat_seconds = heartbeat_seconds
        self.globals = GlobalCounters()
        self._heartbeat_task: asyncio.Task | None = None
        self._pool: WorkerPool | None = None

    def bind_pool(self, pool: WorkerPool) -> None:
        self._pool = pool

    # --- event writers ---
    def _emit(self, ev: dict[str, Any]) -> None:
        ev["ts"] = round(time.time(), 3)
        try:
            self._jsonl_fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            log.debug("metrics emit failed: %s", e)

    def probe_event(
        self,
        worker_id: str,
        external_ip: str | None,
        clean: bool,
        marker: str,
        latency_ms: int,
        organic_count: int,
        http_status: int,
        unresponsive: list[str] | None = None,
    ) -> None:
        self.globals.probe_total += 1
        if clean:
            self.globals.probe_clean += 1
        self._emit({
            "ev": "probe",
            "worker": worker_id,
            "ext_ip": external_ip,
            "clean": clean,
            "marker": marker,
            "latency_ms": latency_ms,
            "organic": organic_count,
            "http": http_status,
            "unresponsive": unresponsive or [],
        })

    def connect_event(
        self,
        worker_id: str,
        target: str,
        source: str,  # "main" or "probe-N"
        ok: bool,
        bytes_up: int,
        bytes_down: int,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        if source == "main":
            self.globals.connect_main_total += 1
            self.globals.connect_main_recent.append(time.monotonic())
        else:
            self.globals.connect_probe_total += 1
        self._emit({
            "ev": "connect",
            "worker": worker_id,
            "target": target,
            "source": source,
            "ok": ok,
            "bytes_up": bytes_up,
            "bytes_down": bytes_down,
            "duration_ms": duration_ms,
            "error": error,
        })

    def connect_rejected(self, source: str, status: int, reason: str) -> None:
        if source == "main":
            if status == 503:
                self.globals.connect_main_503 += 1
            elif status == 502:
                self.globals.connect_main_502 += 1
        else:
            self.globals.connect_probe_502 += 1
        self._emit({
            "ev": "reject",
            "source": source,
            "status": status,
            "reason": reason,
        })

    def state_event(
        self,
        worker_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> None:
        self._emit({
            "ev": "state",
            "worker": worker_id,
            "from": from_state,
            "to": to_state,
            "reason": reason,
        })

    def acquire_latency(self, ms: int) -> None:
        self.globals.acquire_latency_ms.append(ms)

    # --- heartbeat ---
    async def start_heartbeat(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            self._jsonl_fh.flush()
            self._jsonl_fh.close()
        except Exception:
            pass

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.heartbeat_seconds)
                if self._pool is None:
                    continue
                snap = self.pool_snapshot()
                line = (
                    f"[router] up={self.globals.uptime_s()}s  "
                    f"active={snap['active_count']}/{self._pool.config.target_active}  "
                    f"reserve={snap['reserve_count']}  "
                    f"cooldown={snap['cooldown_count']}  "
                    f"draining={snap['draining_count']}  "
                    f"probing={snap['probing_count']}  "
                    f"pool_clean={int(snap['pool_clean_pct']*100)}%  "
                    f"connect_1m={self.globals.connect_rate_1m():.2f}/s  "
                    f"acquire_p95={self.globals.acquire_p95_ms()}ms  "
                    f"inflight={snap['inflight_total']}"
                )
                print(line, flush=True)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                log.debug("heartbeat error: %s", e)

    # --- snapshots ---
    def pool_snapshot(self) -> dict[str, Any]:
        if self._pool is None:
            return {}
        from .worker import WorkerState

        per_state: dict[str, int] = {s.value: 0 for s in WorkerState}
        inflight_total = 0
        clean_pcts: list[float] = []
        per_pool: dict[str, dict[str, int]] = {
            "ru": {"total": 0, "active": 0, "probes_clean_sum": 0, "probes_total_sum": 0},
            "pl": {"total": 0, "active": 0, "probes_clean_sum": 0, "probes_total_sum": 0},
        }
        for w in self._pool.workers:
            per_state[w.state.value] += 1
            inflight_total += w.inflight_count()
            if w.state == WorkerState.ACTIVE and w.metrics.probes_total > 0:
                clean_pcts.append(w.metrics.clean_pct())
            pool_tag = w.short_id.rsplit("-", 1)[-1] if "-" in w.short_id else "?"
            if pool_tag in per_pool:
                per_pool[pool_tag]["total"] += 1
                if w.state == WorkerState.ACTIVE:
                    per_pool[pool_tag]["active"] += 1
                per_pool[pool_tag]["probes_clean_sum"] += w.metrics.probes_clean
                per_pool[pool_tag]["probes_total_sum"] += w.metrics.probes_total
        return {
            "active_count": per_state["active"],
            "reserve_count": per_state["reserve"],
            "cooldown_count": per_state["cooldown"],
            "draining_count": per_state["draining"],
            "probing_count": per_state["probing_initial"],
            "retired_count": per_state["retired"],
            "inflight_total": inflight_total,
            "pool_clean_pct": (sum(clean_pcts) / len(clean_pcts)) if clean_pcts else 0.0,
            "by_pool": per_pool,
        }

    def http_metrics_json(self) -> bytes:
        """JSON-snapshot для HTTP /metrics."""
        pool_snap = self.pool_snapshot()
        out = {
            "uptime_s": self.globals.uptime_s(),
            "connect": {
                "main_total": self.globals.connect_main_total,
                "main_503": self.globals.connect_main_503,
                "main_502": self.globals.connect_main_502,
                "probe_total": self.globals.connect_probe_total,
                "probe_502": self.globals.connect_probe_502,
                "rate_1m": round(self.globals.connect_rate_1m(), 3),
            },
            "probe": {
                "total": self.globals.probe_total,
                "clean": self.globals.probe_clean,
                "clean_pct": round(self.globals.probe_clean_pct(), 3),
            },
            "acquire": {
                "p95_ms": self.globals.acquire_p95_ms(),
            },
            "pool": pool_snap,
            "workers": [w.snapshot() for w in (self._pool.workers if self._pool else [])],
        }
        return (json.dumps(out, indent=2, ensure_ascii=False)).encode("utf-8")
