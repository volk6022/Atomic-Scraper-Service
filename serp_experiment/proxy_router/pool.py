"""WorkerPool — менеджмент пула воркеров, scheduler, LRU selection, drain."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .worker import Worker, WorkerState

if TYPE_CHECKING:
    from .config import RouterConfig
    from .health import HealthProber
    from .metrics import MetricsCollector


log = logging.getLogger(__name__)


def load_proxies_from_file(path: Path) -> list[str]:
    """Прочитать список socks5/http URL из файла (по одному на строку, без пустых и комментариев)."""
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


class WorkerPool:
    def __init__(
        self,
        config: RouterConfig,
        prober: HealthProber,
        metrics: MetricsCollector,
    ) -> None:
        self.config = config
        self.prober = prober
        self.metrics = metrics

        proxies = load_proxies_from_file(config.proxies_file)
        if not proxies:
            raise RuntimeError(f"no proxies in {config.proxies_file}")
        if len(proxies) < config.total_workers:
            log.warning(
                "proxies file has %d entries, need %d — будет меньше worker'ов чем целевое",
                len(proxies), config.total_workers,
            )
        # Берём только сколько нужно (или сколько есть)
        self.workers: list[Worker] = [
            Worker(socks5_url=u, config=config)
            for u in proxies[:config.total_workers]
        ]

        self._lock = asyncio.Lock()
        self._cond = asyncio.Condition(self._lock)
        self._scheduler_task: asyncio.Task | None = None
        self._probe_task: asyncio.Task | None = None
        self._ipify_task: asyncio.Task | None = None
        self._stopped = False

    # ---- lifecycle ----
    async def start(self) -> None:
        # Все воркеры стартуют в PROBING_INITIAL. Через несколько проб
        # scheduler promote их в ACTIVE / RESERVE.
        for w in self.workers:
            w.state = WorkerState.PROBING_INITIAL
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._probe_task = asyncio.create_task(self._probe_loop())
        self._ipify_task = asyncio.create_task(self._ipify_loop())
        log.info("WorkerPool started with %d workers", len(self.workers))

    async def stop(self) -> None:
        self._stopped = True
        for t in (self._scheduler_task, self._probe_task, self._ipify_task):
            if t:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    # ---- acquire (LRU) ----
    async def acquire(self) -> Worker | None:
        """Выбрать ACTIVE worker'а: LRU (last_assigned_ts ASC) + tie-break по inflight.

        Ждёт ≤ acquire_timeout если нет ACTIVE'ов. Возвращает None при таймауте.
        Если active=0, но reserve>0 — ad-hoc promote reserve.
        """
        deadline = time.monotonic() + self.config.acquire_timeout
        t_wait_start = time.monotonic()
        try:
            async with self._cond:
                while True:
                    candidate = self._pick_active_locked()
                    if candidate is None:
                        # fallback: попробовать promote из reserve
                        promoted = self._promote_one_reserve_locked(reason="active_empty")
                        if promoted is not None:
                            candidate = promoted
                    if candidate is not None:
                        candidate.record_select()
                        latency_ms = int((time.monotonic() - t_wait_start) * 1000)
                        self.metrics.acquire_latency(latency_ms)
                        return candidate
                    # ждём notify или timeout
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        return None
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        return None
        except Exception as e:  # noqa: BLE001
            log.warning("acquire error: %s", e)
            return None

    def _pick_active_locked(self) -> Worker | None:
        """Под self._lock: выбрать ACTIVE worker'а по LRU + tie-break."""
        candidates = [w for w in self.workers if w.state == WorkerState.ACTIVE and w.can_accept()]
        if not candidates:
            return None
        # LRU: last_assigned_ts ASC. Tie-break: inflight_count ASC.
        candidates.sort(key=lambda w: (w.last_assigned_ts, w.inflight_count()))
        return candidates[0]

    def _promote_one_reserve_locked(self, reason: str = "promote") -> Worker | None:
        for w in self.workers:
            if w.state == WorkerState.RESERVE:
                self._change_state_locked(w, WorkerState.ACTIVE, reason)
                return w
        return None

    def _change_state_locked(self, w: Worker, new_state: WorkerState, reason: str) -> None:
        old = w.state.value
        w.state = new_state
        self.metrics.state_event(w.short_id, old, new_state.value, reason)

    # ---- scheduler loop ----
    async def _scheduler_loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(self.config.scheduler_tick_seconds)
                await self._scheduler_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                log.warning("scheduler error: %s", e)

    async def _scheduler_tick(self) -> None:
        now = time.monotonic()
        retire_tasks: list[Worker] = []
        async with self._cond:
            # Counts:
            active_n = sum(1 for w in self.workers if w.state == WorkerState.ACTIVE)
            reserve_n = sum(1 for w in self.workers if w.state == WorkerState.RESERVE)

            # 1) ACTIVE: TTL истёк или clean_pct упал
            for w in self.workers:
                if w.state == WorkerState.ACTIVE:
                    if now > w.expires_at:
                        retire_tasks.append(w)
                        self._change_state_locked(
                            w, WorkerState.DRAINING, "ttl_expired"
                        )
                    elif (
                        w.metrics.probes_total >= 5
                        and w.metrics.clean_pct() < self.config.min_clean_pct
                    ):
                        retire_tasks.append(w)
                        self._change_state_locked(
                            w, WorkerState.DRAINING, "dirty"
                        )

            # 2) COOLDOWN с истёкшим таймером → PROBING_INITIAL (новый цикл)
            for w in self.workers:
                if w.state == WorkerState.COOLDOWN and (w.cooldown_until is not None) and now >= w.cooldown_until:
                    # reset TTL для нового цикла
                    w.born_at = now
                    w.expires_at = now + self.config.worker_ttl_seconds
                    w.cooldown_until = None
                    # очистка clean_window для нового цикла (новая sticky session = новый IP)
                    w.metrics.clean_window.clear()
                    self._change_state_locked(
                        w, WorkerState.PROBING_INITIAL, "cooldown_done"
                    )

            # 3) PROBING_INITIAL с 2+ чистыми пробами → ACTIVE/RESERVE
            for w in self.workers:
                if w.state == WorkerState.PROBING_INITIAL:
                    clean_count = sum(1 for c in w.metrics.clean_window if c)
                    total = len(w.metrics.clean_window)
                    if total >= 2 and clean_count >= 2 and w.metrics.clean_pct() >= self.config.min_clean_pct:
                        target = WorkerState.ACTIVE if active_n < self.config.target_active else WorkerState.RESERVE
                        self._change_state_locked(w, target, "promoted_clean")
                        if target == WorkerState.ACTIVE:
                            active_n += 1
                        else:
                            reserve_n += 1

            # 4) RESERVE → ACTIVE если active не добор
            while active_n < self.config.target_active:
                promoted = self._promote_one_reserve_locked("fill_active")
                if promoted is None:
                    break
                active_n += 1
                reserve_n -= 1

            self._cond.notify_all()

        # Запуск drain'ов вне lock'а (drain ждёт inflight, может быть долго)
        for w in retire_tasks:
            asyncio.create_task(self._drain_and_cooldown(w))

    async def _drain_and_cooldown(self, w: Worker) -> None:
        try:
            await w.drain(self.config.drain_timeout)
        finally:
            # rest period с jitter'ом
            low = self.config.cooldown_jitter_low
            high = self.config.cooldown_jitter_high
            pm = self.config.cooldown_jitter_pm
            base = random.uniform(low, high)
            jitter = random.uniform(-pm, pm)
            sec = max(
                self.config.cooldown_clamp_min,
                min(self.config.cooldown_clamp_max, base + jitter),
            )
            async with self._cond:
                w.cooldown_until = time.monotonic() + sec
                self._change_state_locked(
                    w, WorkerState.COOLDOWN, f"drain_done_rest_{int(sec)}s"
                )
                self._cond.notify_all()

    # ---- probe loop ----
    async def _probe_loop(self) -> None:
        # Staggered cold start: первая проба для каждого воркера со смещением i*1s
        await asyncio.sleep(0.5)  # дать stack'у подняться
        # Запускаем по таску на воркер — каждый сам определяет свой interval
        per_worker_tasks: list[asyncio.Task] = []
        for i, w in enumerate(self.workers):
            t = asyncio.create_task(self._probe_one_worker_loop(w, initial_delay=i * 1.0))
            per_worker_tasks.append(t)
        try:
            await asyncio.gather(*per_worker_tasks)
        except asyncio.CancelledError:
            for t in per_worker_tasks:
                t.cancel()
            raise

    async def _probe_one_worker_loop(self, w: Worker, initial_delay: float) -> None:
        await asyncio.sleep(initial_delay)
        while not self._stopped:
            try:
                # пропускаем DRAINING / RETIRED / COOLDOWN — нет смысла probе'ить
                if w.state in (WorkerState.DRAINING, WorkerState.RETIRED, WorkerState.COOLDOWN):
                    await asyncio.sleep(self.config.scheduler_tick_seconds)
                    continue

                await self.prober.probe(w)

                # На основе свежей пробы можем сразу нотифицировать pool
                # (например, PROBING_INITIAL только что собрал 2-ю clean пробу → пора promote)
                async with self._cond:
                    self._cond.notify_all()

                # Подбираем next interval
                if w.state == WorkerState.PROBING_INITIAL:
                    interval = self.config.probe_interval_initial
                elif w.metrics.clean_pct() >= 0.95:
                    interval = self.config.probe_interval_active_healthy
                else:
                    interval = self.config.probe_interval_active_unstable
                # лёгкий jitter ±10%, чтобы не пробить все 20 одновременно
                interval *= random.uniform(0.9, 1.1)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                log.warning("probe loop for %s error: %s", w.short_id, e)
                await asyncio.sleep(5)

    # ---- external IP loop ----
    async def _ipify_loop(self) -> None:
        # Раз в N секунд обходим все воркеры и обновляем external_ip.
        # Без блокирования — fire-and-forget tasks.
        await asyncio.sleep(20)  # дать probe-pipeline'у разогнаться сначала
        while not self._stopped:
            try:
                tasks = [
                    asyncio.create_task(self.prober.refresh_external_ip(w))
                    for w in self.workers
                    if w.state in (WorkerState.ACTIVE, WorkerState.RESERVE, WorkerState.PROBING_INITIAL)
                ]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(self.config.external_ip_refresh_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                log.debug("ipify loop error: %s", e)
                await asyncio.sleep(60)
