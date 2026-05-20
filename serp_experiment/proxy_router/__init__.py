"""serp_experiment.proxy_router — local async SERP proxy router.

Архитектура:
    SearXNG-prod ─CONNECT─> Router(:8888) ─acquire LRU worker─> socks5 ─> upstream
    SearXNG-probe-i ─CONNECT─> Router(:900i) ─slot_to_worker[i]─> socks5 ─> upstream

См. serp_experiment/REPORT_searxng.md и planning notes для деталей.
"""
from .config import RouterConfig
from .worker import Worker, WorkerState, ProbeResult
from .pool import WorkerPool, load_proxies_from_file
from .probe_slots import ProbeSlotPool, ProbeSlot
from .health import HealthProber
from .metrics import MetricsCollector
from .router import Router

__all__ = [
    "RouterConfig",
    "Worker",
    "WorkerState",
    "ProbeResult",
    "WorkerPool",
    "load_proxies_from_file",
    "ProbeSlotPool",
    "ProbeSlot",
    "HealthProber",
    "MetricsCollector",
    "Router",
]
