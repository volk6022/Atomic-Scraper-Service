"""CLI entrypoint для proxy_router.

Запуск:
    uv run python -m serp_experiment.proxy_router
    uv run python -m serp_experiment.proxy_router --proxies-file ... --probe-slots 4

Перед поднятием Docker-compose'а вызывается `generate_probe_configs(K)` —
шаблонизатор пишет K конфигов в `repos/searxng-deploy/probe/searxng-probe-{i}/`.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .config import RouterConfig
from .health import HealthProber
from .metrics import MetricsCollector
from .pool import WorkerPool
from .probe_slots import ProbeSlotPool
from .router import Router


log = logging.getLogger("proxy_router")


def generate_probe_configs(config: RouterConfig) -> list[Path]:
    """Прочитать probe/template.yml, подставить {{PROBE_PORT}} для каждого слота,
    записать в probe/searxng-probe-{i}/settings.yml. Возвращает список путей.
    """
    template_path = config.probe_template_path
    if not template_path.exists():
        raise RuntimeError(
            f"probe template not found: {template_path}.\n"
            f"Create it first (см. план), затем запусти router снова."
        )
    template_text = template_path.read_text(encoding="utf-8")
    out_paths: list[Path] = []
    for i in range(config.probe_slot_count):
        slot_id = i  # 0-based
        port = config.probe_router_port(slot_id)
        instance_dir = config.probe_config_dir / f"searxng-probe-{slot_id + 1}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        rendered = template_text.replace("{{PROBE_PORT}}", str(port))
        out_path = instance_dir / "settings.yml"
        out_path.write_text(rendered, encoding="utf-8")
        out_paths.append(out_path)
        log.info("generated probe config: %s (port %d)", out_path, port)
    return out_paths


async def amain(config: RouterConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # 1. Генерируем probe-config'и (idempotent).
    log.info("generating probe configs for %d slots...", config.probe_slot_count)
    try:
        generate_probe_configs(config)
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(2)

    # 2. Поднимаем компоненты.
    metrics = MetricsCollector(
        jsonl_path=config.metrics_file,
        heartbeat_seconds=config.heartbeat_seconds,
    )
    slot_pool = ProbeSlotPool(
        slot_count=config.probe_slot_count,
        router_port_base=config.probe_router_port_base,
        searxng_port_base=config.probe_searxng_port_base,
    )
    prober = HealthProber(config=config, slot_pool=slot_pool, metrics=metrics)
    pool = WorkerPool(config=config, prober=prober, metrics=metrics)
    metrics.bind_pool(pool)
    router = Router(config=config, pool=pool, slot_pool=slot_pool, metrics=metrics)

    # 3. Старт.
    await router.start()
    await pool.start()
    await metrics.start_heartbeat()
    log.info("router up, waiting for traffic. Ctrl+C to stop.")

    # 4. Ждём сигнала остановки.
    stop_event = asyncio.Event()

    def _on_signal(signum: int) -> None:
        log.info("received signal %d, shutting down", signum)
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal, sig)
            except (NotImplementedError, ValueError):
                pass
    # на Windows asyncio.add_signal_handler не поддерживается — Ctrl+C
    # будет вылезать как KeyboardInterrupt в await stop_event.wait().

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("interrupted, shutting down")

    # 5. Cleanup.
    log.info("stopping...")
    await router.stop()
    await pool.stop()
    await prober.close()
    await metrics.stop()
    log.info("stopped.")


def main() -> None:
    ap = argparse.ArgumentParser(description="serp_experiment proxy router")
    ap.add_argument("--proxies-file", type=Path, default=None,
                    help="path to file with socks5/http URLs (default: serp_experiment/more_proxes.txt)")
    ap.add_argument("--main-port", type=int, default=None, help="main listener port (default 8888)")
    ap.add_argument("--probe-slots", type=int, default=None, help="K — number of probe slots (default 4)")
    ap.add_argument("--probe-router-port-base", type=int, default=None,
                    help="base port for probe router listeners (default 9001)")
    ap.add_argument("--probe-searxng-port-base", type=int, default=None,
                    help="base port for probe-SearXNG hosts (default 8081)")
    ap.add_argument("--log-level", default=None, help="DEBUG / INFO / WARNING (default INFO)")
    ap.add_argument("--no-metrics-http", action="store_true", help="disable GET /metrics on main")
    ap.add_argument("--generate-only", action="store_true",
                    help="just generate probe-configs and exit (no router start)")
    args = ap.parse_args()

    config = RouterConfig()
    if args.proxies_file is not None:
        config.proxies_file = args.proxies_file
    if args.main_port is not None:
        config.main_port = args.main_port
    if args.probe_slots is not None:
        config.probe_slot_count = args.probe_slots
    if args.probe_router_port_base is not None:
        config.probe_router_port_base = args.probe_router_port_base
    if args.probe_searxng_port_base is not None:
        config.probe_searxng_port_base = args.probe_searxng_port_base
    if args.log_level:
        config.log_level = args.log_level
    if args.no_metrics_http:
        config.metrics_http_enabled = False

    if args.generate_only:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
        paths = generate_probe_configs(config)
        for p in paths:
            print(p)
        return

    try:
        asyncio.run(amain(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
