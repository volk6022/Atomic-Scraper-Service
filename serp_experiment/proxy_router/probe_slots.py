"""ProbeSlotPool — K-местный пул probe-слотов.

Каждый слот = пара (router probe-port, probe-SearXNG port). Используется
HealthProber'ом для атомарного per-worker probe'а:
    1. acquire slot
    2. router.set_slot_worker(slot, worker)  ← мутабельное mapping
    3. GET probe-SearXNG (which proxies through router:slot.router_port → worker)
    4. release slot

LIFO для cache-locality: последний только что отработавший probe-SearXNG warm
(httpx-keepalive внутри контейнера ещё свеж).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .worker import Worker


@dataclass
class ProbeSlot:
    id: int                # 0..K-1
    router_port: int       # 9001..9000+K
    searxng_port: int      # 8081..8080+K


class ProbeSlotPool:
    def __init__(
        self,
        slot_count: int,
        router_port_base: int,
        searxng_port_base: int,
    ) -> None:
        self.slot_count = slot_count
        self.slots: list[ProbeSlot] = [
            ProbeSlot(
                id=i,
                router_port=router_port_base + i,
                searxng_port=searxng_port_base + i,
            )
            for i in range(slot_count)
        ]
        # LIFO стек свободных slot-id
        self._free: list[int] = list(range(slot_count - 1, -1, -1))  # K-1, ..., 1, 0
        self._sem = asyncio.Semaphore(slot_count)
        self._lock = asyncio.Lock()
        # mutable mapping slot_id -> Worker (или None если свободен)
        self.slot_to_worker: dict[int, Worker | None] = {i: None for i in range(slot_count)}

    async def acquire(self) -> ProbeSlot:
        await self._sem.acquire()
        async with self._lock:
            slot_id = self._free.pop()  # LIFO
            return self.slots[slot_id]

    async def release(self, slot_id: int) -> None:
        async with self._lock:
            self.slot_to_worker[slot_id] = None
            self._free.append(slot_id)
        self._sem.release()

    def set_worker(self, slot_id: int, worker: Worker | None) -> None:
        # без lock — это write по dict-key, в CPython атомарно;
        # читается из router'а в горячем пути без lock'а
        self.slot_to_worker[slot_id] = worker

    def get_worker(self, slot_id: int) -> Worker | None:
        return self.slot_to_worker.get(slot_id)
