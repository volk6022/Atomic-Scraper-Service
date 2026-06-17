"""Изолированный тест router'а + probe pipeline.

Запускается ОТДЕЛЬНО, при условии что:
  - router крутится (`uv run python -m serp_experiment.proxy_router`)
  - probe-SearXNG'и подняты (`docker compose up -d` в repos/searxng-deploy)

Что делает:
  1. Поднимает локальные wrapper'ы поверх router'а (свои Worker/HealthProber/etc.)
     Нет — это слишком сложно. Вместо этого: дёргает HTTP /metrics router'а
     чтобы получить список воркеров, и затем через probe-SearXNG endpoint'ы
     напрямую делает N=50 параллельных запросов, рандомизируя slot.
  2. Печатает per-worker probe clean rate (что-нибудь, что мы видим в /metrics),
     plus our own measurements (success rate, latency).

Главная цель: убедиться, что probe-инфраструктура работает синхронно и
LRU/round-robin на main-listener'е тоже работает (через /metrics видим
selected_5m по воркерам).

Usage:
    uv run python -m serp_experiment.test_router_isolated
    uv run python -m serp_experiment.test_router_isolated --concurrent 50 --probes 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from typing import Any

import httpx


async def fetch_metrics(client: httpx.AsyncClient, base: str = "http://localhost:8888") -> dict[str, Any]:
    resp = await client.get(f"{base}/metrics", timeout=10)
    resp.raise_for_status()
    return resp.json()


async def one_probe(
    client: httpx.AsyncClient,
    probe_searxng_port: int,
    query: str,
) -> dict[str, Any]:
    """Один probe — httpx GET на probe-SearXNG. Возвращает {ok, organic, latency_ms, status}."""
    url = (
        f"http://localhost:{probe_searxng_port}/search"
        f"?q={query}&format=json&language=en"
    )
    t0 = time.perf_counter()
    try:
        resp = await client.get(url, headers={"Accept": "application/json"}, timeout=20)
        dt_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            return {"ok": False, "organic": 0, "latency_ms": dt_ms, "status": resp.status_code, "err": "http"}
        data = resp.json()
        organic = data.get("results") or []
        unresponsive = data.get("unresponsive_engines") or []
        return {
            "ok": len(organic) >= 3,
            "organic": len(organic),
            "latency_ms": dt_ms,
            "status": resp.status_code,
            "unresponsive": [item[0] if isinstance(item, (list, tuple)) else str(item) for item in unresponsive],
        }
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "organic": 0, "latency_ms": dt_ms, "status": 0, "err": f"{type(e).__name__}: {e}"}


async def amain() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrent", type=int, default=4, help="parallel probes (≤ probe_slots)")
    ap.add_argument("--probes", type=int, default=50, help="total probes")
    ap.add_argument(
        "--probe-ports",
        nargs="+",
        type=int,
        default=[8081, 8082, 8083, 8084],
        help="probe-SearXNG ports (default 8081..8084)",
    )
    ap.add_argument(
        "--queries",
        nargs="+",
        default=[
            "probe ping ip clean check",
            "python asyncio tutorial",
            "best coffee shops",
            "what is artificial intelligence",
            "weather forecast tomorrow",
        ],
        help="rotation of test queries",
    )
    ap.add_argument("--router-base", default="http://localhost:8888")
    args = ap.parse_args()

    async with httpx.AsyncClient() as client:
        # 0. Получаем snapshot воркеров и probe-readiness
        print("=== Router /metrics snapshot (before) ===")
        try:
            m = await fetch_metrics(client, args.router_base)
            print(f"uptime: {m['uptime_s']}s")
            print(f"pool: {m['pool']}")
            print(f"probe_total: {m['probe']['total']}  clean_pct: {m['probe']['clean_pct']}")
            print(f"active workers: {m['pool']['active_count']}")
        except Exception as e:
            print(f"!!! cannot reach router /metrics: {e}")
            print(f"!!! is router running? `uv run python -m serp_experiment.proxy_router`")
            return

        # 1. N параллельных probe'ов
        sem = asyncio.Semaphore(args.concurrent)
        results: list[dict[str, Any]] = []

        async def _one(i: int) -> None:
            async with sem:
                port = random.choice(args.probe_ports)
                query = args.queries[i % len(args.queries)]
                r = await one_probe(client, port, query)
                r["port"] = port
                r["i"] = i
                tag = "OK  " if r["ok"] else "FAIL"
                print(
                    f"  [{i+1:>3}/{args.probes}] {tag}  port={port}  "
                    f"{r['latency_ms']:5d}ms  organic={r['organic']:>2}  "
                    f"status={r['status']}",
                    flush=True,
                )
                results.append(r)

        print(f"\n=== Running {args.probes} probes, concurrency={args.concurrent} ===")
        t_start = time.perf_counter()
        await asyncio.gather(*(_one(i) for i in range(args.probes)))
        elapsed = time.perf_counter() - t_start

        # 2. Summary
        ok = [r for r in results if r["ok"]]
        latencies = [r["latency_ms"] for r in results]
        latencies_ok = [r["latency_ms"] for r in ok]
        organic = [r["organic"] for r in ok]
        success_pct = 100.0 * len(ok) / len(results) if results else 0
        print("\n=== Summary ===")
        print(f"total: {len(results)}  ok: {len(ok)}  success: {success_pct:.1f}%")
        print(f"elapsed: {elapsed:.1f}s  rps: {len(results)/max(elapsed, 0.1):.2f}")
        if latencies:
            print(
                f"latency_ms  mean={statistics.mean(latencies):.0f}  "
                f"median={statistics.median(latencies):.0f}  "
                f"min={min(latencies)}  max={max(latencies)}"
            )
        if latencies_ok:
            print(f"latency_ms (ok only)  mean={statistics.mean(latencies_ok):.0f}  median={statistics.median(latencies_ok):.0f}")
        if organic:
            print(f"organic  mean={statistics.mean(organic):.1f}  median={statistics.median(organic):.1f}")

        # per-port histogram
        from collections import Counter
        per_port_total: Counter = Counter()
        per_port_ok: Counter = Counter()
        for r in results:
            per_port_total[r["port"]] += 1
            if r["ok"]:
                per_port_ok[r["port"]] += 1
        print("\nper-probe-port:")
        for port in sorted(per_port_total):
            t = per_port_total[port]
            o = per_port_ok[port]
            pct = 100.0 * o / t if t else 0
            print(f"  port {port}: {o}/{t} ({pct:.0f}%)")

        # 3. router /metrics snapshot (after) — посмотреть, как pool изменился
        print("\n=== Router /metrics snapshot (after) ===")
        try:
            m2 = await fetch_metrics(client, args.router_base)
            print(f"uptime: {m2['uptime_s']}s")
            print(f"probe_total: {m2['probe']['total']}  clean_pct: {m2['probe']['clean_pct']}")
            print(f"pool: {m2['pool']}")
            print("\nper-worker (top 10 by selected_5m):")
            workers = sorted(
                m2.get("workers", []),
                key=lambda w: w.get("selected_5m", 0),
                reverse=True,
            )
            for w in workers[:10]:
                print(
                    f"  {w['id']:30s} state={w['state']:14s} "
                    f"clean={w['clean_pct_window']:.2f} probes={w['probes_total']:>3} "
                    f"selected_5m={w['selected_5m']:>3} ip={w.get('external_ip')}"
                )
        except Exception as e:
            print(f"!!! cannot fetch post-metrics: {e}")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
