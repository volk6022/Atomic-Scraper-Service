"""Worker — обёртка над одним upstream socks5 с FSM и per-worker метриками.

Состояния:
    PROBING_INITIAL → ACTIVE ↔ RESERVE ↔ COOLDOWN → DRAINING → RETIRED
                          ↑                                       │
                          └───────────────────────────────────────┘
                              (после COOLDOWN → PROBING_INITIAL новый цикл)
"""
from __future__ import annotations

import asyncio
import enum
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from python_socks.async_.asyncio import Proxy as AsyncSocksProxy


class WorkerState(enum.Enum):
    PROBING_INITIAL = "probing_initial"
    ACTIVE = "active"
    RESERVE = "reserve"
    COOLDOWN = "cooldown"
    DRAINING = "draining"
    RETIRED = "retired"


@dataclass
class ProbeResult:
    clean: bool
    latency_ms: int
    marker: str  # "ok" | "empty" | "blocked" | "http_5xx" | "timeout" | "no_engines" | ...
    organic_count: int = 0
    http_status: int = 0
    unresponsive: list[str] = field(default_factory=list)


@dataclass
class WorkerMetrics:
    probes_total: int = 0
    probes_clean: int = 0
    connect_total: int = 0
    connect_ok: int = 0
    connect_fail_socks: int = 0
    connect_fail_other: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    probe_latency_ms: deque = field(default_factory=lambda: deque(maxlen=50))
    clean_window: deque = field(default_factory=lambda: deque(maxlen=20))  # bool'ы
    selected_recent: deque = field(default_factory=lambda: deque(maxlen=200))  # timestamps

    def clean_pct(self) -> float:
        if not self.clean_window:
            return 0.0
        return sum(1 for c in self.clean_window if c) / len(self.clean_window)

    def probe_latency_p50_ms(self) -> int:
        if not self.probe_latency_ms:
            return 0
        s = sorted(self.probe_latency_ms)
        return int(s[len(s) // 2])

    def probe_latency_p95_ms(self) -> int:
        if not self.probe_latency_ms:
            return 0
        s = sorted(self.probe_latency_ms)
        idx = max(0, int(round(0.95 * (len(s) - 1))))
        return int(s[idx])

    def selected_in_last_5m(self) -> int:
        now = time.monotonic()
        cutoff = now - 300
        return sum(1 for ts in self.selected_recent if ts >= cutoff)


def _short_id(socks5_url: str) -> str:
    """Короткий человеко-читаемый id: 'host:port-userhint'.

    Из 'socks5://...__cr.ru;sessttl.10:...@np.puls-proxy.com:11005' получаем
    'np.puls-proxy.com:11005-ru'.
    """
    try:
        parsed = urlparse(socks5_url)
        host = parsed.hostname or "?"
        port = parsed.port or 0
        user = (parsed.username or "").split(";", 1)[0]
        pool = "ru" if user.endswith(".ru") else ("pl" if user.endswith(".pl") else "?")
        return f"{host}:{port}-{pool}"
    except Exception:
        return socks5_url


class Worker:
    """Один upstream socks5: FSM + метрики + open_tunnel."""

    def __init__(self, socks5_url: str, config) -> None:
        self.socks5_url = socks5_url
        self.short_id = _short_id(socks5_url)
        self.config = config

        self.state: WorkerState = WorkerState.PROBING_INITIAL
        self.born_at: float = time.monotonic()
        self.expires_at: float = self.born_at + config.worker_ttl_seconds
        self.cooldown_until: float | None = None
        self.last_assigned_ts: float = 0.0  # для LRU; 0 = ещё ни разу не выбран
        self.inflight: set[asyncio.Task[Any]] = set()
        self.external_ip: str | None = None  # узнаётся опционально

        self.metrics = WorkerMetrics()

        # event для уведомления о завершении drain (если кому надо ждать)
        self._drain_done: asyncio.Event = asyncio.Event()
        self._drain_done.set()  # изначально не drain'имся

    # ---- селектор ----
    def can_accept(self) -> bool:
        if self.state != WorkerState.ACTIVE:
            return False
        # PROBING_INITIAL воркеры не имеют clean_window достаточного размера —
        # этот check для ACTIVE с накопленной статистикой.
        if self.metrics.probes_total == 0:
            return True  # только что промоутнут, ещё не успел проба прийти
        return self.metrics.clean_pct() >= self.config.min_clean_pct

    def inflight_count(self) -> int:
        return len(self.inflight)

    def ttl_remaining(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())

    def cooldown_remaining(self) -> float:
        if self.cooldown_until is None:
            return 0.0
        return max(0.0, self.cooldown_until - time.monotonic())

    # ---- открытие туннеля ----
    async def open_tunnel(
        self, dest_host: str, dest_port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Открыть upstream socks5 tunnel. Поднимает исключение при сбое."""
        proxy = AsyncSocksProxy.from_url(self.socks5_url)
        upstream_sock = await proxy.connect(
            dest_host=dest_host, dest_port=dest_port
        )
        up_reader, up_writer = await asyncio.open_connection(sock=upstream_sock)
        self.metrics.connect_total += 1
        return up_reader, up_writer

    def record_select(self) -> None:
        self.last_assigned_ts = time.monotonic()
        self.metrics.selected_recent.append(self.last_assigned_ts)

    def record_connect_ok(self) -> None:
        self.metrics.connect_ok += 1

    def record_connect_fail(self, kind: str) -> None:
        if kind == "socks":
            self.metrics.connect_fail_socks += 1
        else:
            self.metrics.connect_fail_other += 1

    def record_bytes(self, up: int, down: int) -> None:
        self.metrics.bytes_up += up
        self.metrics.bytes_down += down

    def record_probe(self, result: ProbeResult) -> None:
        self.metrics.probes_total += 1
        if result.clean:
            self.metrics.probes_clean += 1
        self.metrics.clean_window.append(result.clean)
        if result.latency_ms > 0:
            self.metrics.probe_latency_ms.append(result.latency_ms)

    # ---- inflight tracking ----
    def register_inflight(self, task: asyncio.Task[Any]) -> None:
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)
        if self._drain_done.is_set() is True and self.state == WorkerState.DRAINING:
            # на всякий случай: если drain уже завершился, не должны принимать новые.
            # но это вырожденный случай, обычно register_inflight идёт раньше drain.
            pass

    # ---- drain (вызывается из WorkerPool.schedule_retire) ----
    async def drain(self, timeout: float) -> None:
        """Перевести в DRAINING, дождаться завершения in-flight, force-close оставшихся."""
        self.state = WorkerState.DRAINING
        self._drain_done.clear()
        try:
            if self.inflight:
                # ждём до timeout — спокойного завершения inflight
                pending = list(self.inflight)
                try:
                    await asyncio.wait(pending, timeout=timeout)
                except Exception:
                    pass
            # принудительно отменяем оставшихся
            still = list(self.inflight)
            for t in still:
                t.cancel()
            # коротко ждём, чтобы cancel'ы пробились
            if still:
                try:
                    await asyncio.wait(still, timeout=2.0)
                except Exception:
                    pass
        finally:
            self._drain_done.set()

    # ---- сериализация для /metrics ----
    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.short_id,
            "state": self.state.value,
            "external_ip": self.external_ip,
            "born_at_ago_s": int(time.monotonic() - self.born_at),
            "ttl_remaining_s": int(self.ttl_remaining()),
            "cooldown_remaining_s": int(self.cooldown_remaining()),
            "probes_total": self.metrics.probes_total,
            "probes_clean": self.metrics.probes_clean,
            "clean_pct_window": round(self.metrics.clean_pct(), 3),
            "connect_total": self.metrics.connect_total,
            "connect_ok": self.metrics.connect_ok,
            "connect_fail_socks": self.metrics.connect_fail_socks,
            "connect_fail_other": self.metrics.connect_fail_other,
            "bytes_up": self.metrics.bytes_up,
            "bytes_down": self.metrics.bytes_down,
            "probe_p50_ms": self.metrics.probe_latency_p50_ms(),
            "probe_p95_ms": self.metrics.probe_latency_p95_ms(),
            "selected_5m": self.metrics.selected_in_last_5m(),
            "inflight": len(self.inflight),
        }
