"""Конфиг router'а. Все ручки в одном dataclass с дефолтами."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Корень serp_experiment (для дефолтных путей)
_SERP_EXP = Path(__file__).resolve().parents[1]


@dataclass
class RouterConfig:
    # --- Прокси пула ---
    proxies_file: Path = field(default_factory=lambda: _SERP_EXP / "more_proxes.txt")

    # --- Listener'ы ---
    listen_host: str = "0.0.0.0"
    main_port: int = 8888
    probe_router_port_base: int = 9001   # K listener'ов на 9001..9000+K
    probe_searxng_port_base: int = 8081  # K probe-SearXNG'ов на 8081..8080+K
    probe_slot_count: int = 4            # K — количество probe-слотов / probe-SearXNG'ов

    # --- Pool sizing ---
    target_active: int = 15              # 75% от 20
    target_reserve: int = 5              # 25% от 20

    # --- TTL / lifecycle ---
    worker_ttl_seconds: int = 9 * 60 + 45  # 9m45s — sessttl.10 с запасом
    cooldown_jitter_low: int = 15
    cooldown_jitter_high: int = 30
    cooldown_jitter_pm: int = 10           # ±10 к (low..high) → итог clamp [5..40]
    cooldown_clamp_min: int = 5
    cooldown_clamp_max: int = 40

    # --- Probe тайминги ---
    probe_interval_active_healthy: int = 90  # для ACTIVE с clean_pct >= 0.95
    probe_interval_active_unstable: int = 30  # для ACTIVE с clean_pct < 0.95
    probe_interval_initial: int = 5           # для PROBING_INITIAL
    probe_clean_window: int = 20              # размер sliding-window для clean_pct
    min_clean_pct: float = 0.80               # порог can_accept / retire

    # --- Probe запрос ---
    probe_query: str = "probe ping ip clean check"
    probe_min_organic: int = 3                # минимум organic для clean
    probe_http_timeout: float = 15.0          # timeout на probe-SearXNG /search

    # --- External IP detection ---
    external_ip_refresh_seconds: int = 300
    external_ip_url: str = "https://api.ipify.org"

    # --- Acquire / drain ---
    acquire_timeout: float = 2.0
    drain_timeout: float = 30.0

    # --- Scheduler tick ---
    scheduler_tick_seconds: float = 5.0
    heartbeat_seconds: float = 10.0

    # --- Метрики ---
    metrics_file: Path = field(default_factory=lambda: _SERP_EXP / "router.jsonl")
    metrics_http_enabled: bool = True

    # --- Probe-config шаблонизация ---
    probe_template_path: Path = field(
        default_factory=lambda: _SERP_EXP
        / "repos" / "searxng-deploy" / "probe" / "template.yml"
    )
    probe_config_dir: Path = field(
        default_factory=lambda: _SERP_EXP / "repos" / "searxng-deploy" / "probe"
    )

    # --- Run-time ---
    log_level: str = "INFO"

    @property
    def total_workers(self) -> int:
        return self.target_active + self.target_reserve

    def probe_router_port(self, slot_id: int) -> int:
        """slot_id 0-based -> 9001, 9002, ..."""
        return self.probe_router_port_base + slot_id

    def probe_searxng_port(self, slot_id: int) -> int:
        """slot_id 0-based -> 8081, 8082, ..."""
        return self.probe_searxng_port_base + slot_id
