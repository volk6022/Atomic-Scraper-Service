"""Benchmark SERP scraping approaches.

Variants (9 total):
    requests_bs4       × {no_proxy, http_proxy, socks5_proxy}
    playwright_basic   × {no_proxy, http_proxy, socks5_proxy}
    playwright_stealth × {no_proxy, http_proxy, socks5_proxy}

Plus optional sessions mode:
    playwright_basic   × {sessions}
    playwright_stealth × {sessions}

Each variant runs N (default 10) sequential requests. For every request the
script prints latency and a success flag; after the batch it prints mean /
median / success-rate.

Usage:
    uv run python -m serp_experiment.run_benchmark
    uv run python -m serp_experiment.run_benchmark --repeats 5 --query "machine learning"
    uv run python -m serp_experiment.run_benchmark --only requests_bs4
    uv run python -m serp_experiment.run_benchmark --skip playwright_stealth_socks5
    uv run python -m serp_experiment.run_benchmark --use-sessions
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .approaches import (
    playwright_basic,
    playwright_stealth_app,
    requests_bs4,
    searxng_local,
)
from .proxies import get_proxy_url
from .rotating_session import RotatingSessionManager


DEFAULT_QUERY = "What is artificial intelligence"


@dataclass
class RunResult:
    ok: bool
    seconds: float
    organic_count: int = 0
    error: str = ""
    payload: dict[str, Any] | None = None


@dataclass
class VariantResult:
    name: str
    runs: list[RunResult] = field(default_factory=list)


_session_manager: RotatingSessionManager | None = None


def _get_session_manager(sessions_dir: str) -> RotatingSessionManager | None:
    global _session_manager
    if _session_manager is None:
        _session_manager = RotatingSessionManager(sessions_dir)
    return _session_manager


# ----------------------------------------------------------------------------
# Adapters: every approach exposes a single coroutine returning the SERP dict.
# ----------------------------------------------------------------------------


async def _call_sync_in_thread(fn, /, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def run_once_requests(query: str, proxy_url: str | None) -> dict[str, Any]:
    return await _call_sync_in_thread(
        requests_bs4.fetch_serp, query, proxy_url=proxy_url
    )


async def run_once_playwright_basic(
    query: str,
    proxy_url: str | None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await playwright_basic.fetch_serp(
        query, proxy_url=proxy_url, session=session
    )


async def run_once_playwright_stealth(
    query: str,
    proxy_url: str | None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await playwright_stealth_app.fetch_serp(
        query, proxy_url=proxy_url, session=session
    )


async def run_once_searxng(query: str, proxy_url: str | None) -> dict[str, Any]:
    return await _call_sync_in_thread(searxng_local.fetch_serp, query)


VARIANTS: list[tuple[str, Callable[..., Awaitable[dict]], str | None]] = [
    # name                            runner                          proxy kind
    ("searxng_local", run_once_searxng, None),
    ("requests_bs4__no_proxy", run_once_requests, None),
    ("requests_bs4__http", run_once_requests, "http"),
    ("requests_bs4__socks5", run_once_requests, "socks5"),
    ("playwright_basic__no_proxy", run_once_playwright_basic, None),
    ("playwright_basic__http", run_once_playwright_basic, "http"),
    ("playwright_basic__socks5", run_once_playwright_basic, "socks5"),
    ("playwright_stealth__no_proxy", run_once_playwright_stealth, None),
    ("playwright_stealth__http", run_once_playwright_stealth, "http"),
    ("playwright_stealth__socks5", run_once_playwright_stealth, "socks5"),
    # Session-based variants
    ("playwright_basic__sessions", run_once_playwright_basic, "sessions"),
    ("playwright_stealth__sessions", run_once_playwright_stealth, "sessions"),
]


# ----------------------------------------------------------------------------
# Benchmark loop
# ----------------------------------------------------------------------------


async def bench_variant(
    name: str,
    runner: Callable[..., Awaitable[dict]],
    proxy_kind: str | None,
    query: str,
    repeats: int,
    pause_between: float,
    use_sessions: bool = False,
    sessions_dir: str = "sessions",
) -> VariantResult:
    proxy_url: str | None = None
    session: dict[str, Any] | None = None

    if proxy_kind == "sessions":
        if use_sessions:
            manager = _get_session_manager(sessions_dir)
            count = manager.load_sessions()
            if count > 0:
                session = manager.get_current_session()
                proxy_url = session.get("proxy_url") if session else None
                print(f"  using session: {session.get('path', 'unknown')}")
            else:
                print(
                    f"  WARNING: no valid sessions found in {sessions_dir}, falling back to clean browser"
                )
        else:
            print(f"[{name}] skipped — --use-sessions not enabled")
            return VariantResult(name=name)
    elif proxy_kind:
        proxy_url = get_proxy_url(proxy_kind)
        if not proxy_url:
            print(f"[{name}] skipped — no {proxy_kind} proxy in puls file")
            return VariantResult(name=name)
    else:
        proxy_url = None

    print(f"\n=== {name} ===")
    if proxy_kind == "sessions" and session:
        print(f"  session: active ({manager.session_count} total)")
    elif proxy_url:
        try:
            head, host = proxy_url.split("@", 1)
            scheme = head.split("://", 1)[0]
            print(f"proxy: {scheme}://***@{host}")
        except ValueError:
            print(f"proxy: {proxy_url}")
    else:
        print("proxy: <none — direct connection>")

    result = VariantResult(name=name)
    for i in range(1, repeats + 1):
        t0 = time.perf_counter()
        try:
            if proxy_kind == "sessions" and use_sessions:
                payload = await runner(query, None, session)
            else:
                payload = await runner(query, proxy_url)

            dt = time.perf_counter() - t0
            organic = payload.get("organic", [])
            run = RunResult(
                ok=bool(organic),
                seconds=dt,
                organic_count=len(organic),
                payload=payload if i == 1 else None,
            )
            tag = "OK " if run.ok else "EMPTY"
            print(
                f"  [{i:>2}/{repeats}] {tag}  {dt:6.2f}s  organic={run.organic_count}"
            )
        except Exception as e:  # noqa: BLE001
            dt = time.perf_counter() - t0
            run = RunResult(ok=False, seconds=dt, error=f"{type(e).__name__}: {e}")
            print(f"  [{i:>2}/{repeats}] FAIL {dt:6.2f}s  {run.error}")

        result.runs.append(run)

        # Rotate session after each request
        if proxy_kind == "sessions" and use_sessions and _session_manager:
            _session_manager.next_session()
            session = _session_manager.get_current_session()

        if i < repeats and pause_between > 0:
            await asyncio.sleep(pause_between)

    _print_summary(result)
    return result


def _print_summary(r: VariantResult) -> None:
    if not r.runs:
        return
    times = [run.seconds for run in r.runs]
    oks = [run for run in r.runs if run.ok]
    mean = statistics.mean(times)
    median = statistics.median(times)
    success_rate = 100.0 * len(oks) / len(r.runs)
    avg_organic = statistics.mean([run.organic_count for run in oks]) if oks else 0
    print(
        f"  summary: success={len(oks)}/{len(r.runs)} ({success_rate:.0f}%) "
        f"mean={mean:.2f}s median={median:.2f}s avg_organic={avg_organic:.1f}"
    )

    sample = next((run for run in r.runs if run.ok and run.payload), None)
    if sample:
        print("  sample (first 3 organic):")
        for item in sample.payload["organic"][:3]:
            print(f"    #{item['position']} {item['title'][:80]}")
            print(f"        {item['link'][:100]}")
            print(f"        {item['snippet'][:120]}")


def print_grand_summary(results: list[VariantResult]) -> None:
    print("\n" + "=" * 78)
    print("GRAND SUMMARY")
    print("=" * 78)
    header = f"{'variant':40s} {'ok':>7s} {'mean':>8s} {'median':>8s} {'avg_org':>8s}"
    print(header)
    print("-" * 78)
    for r in results:
        if not r.runs:
            print(f"{r.name:40s} {'skipped':>7s}")
            continue
        times = [run.seconds for run in r.runs]
        oks = [run for run in r.runs if run.ok]
        mean = statistics.mean(times)
        median = statistics.median(times)
        avg_organic = statistics.mean([run.organic_count for run in oks]) if oks else 0
        rate = f"{len(oks)}/{len(r.runs)}"
        print(
            f"{r.name:40s} {rate:>7s} {mean:>7.2f}s {median:>7.2f}s {avg_organic:>8.1f}"
        )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    ap.add_argument(
        "--only", default="", help="comma-separated substring filter on variant names"
    )
    ap.add_argument(
        "--skip", default="", help="comma-separated substring filter to exclude"
    )
    ap.add_argument("--save", default="", help="optional path to dump all results JSON")
    ap.add_argument(
        "--use-sessions",
        action="store_true",
        help="Use saved sessions with solved captcha",
    )
    ap.add_argument(
        "--sessions-dir",
        default="sessions",
        help="Directory containing sessions (default: sessions)",
    )
    args = ap.parse_args()

    only = [s for s in args.only.split(",") if s]
    skip = [s for s in args.skip.split(",") if s]

    def keep(name: str) -> bool:
        if only and not any(s in name for s in only):
            return False
        if skip and any(s in name for s in skip):
            return False
        return True

    print(f"Query: {args.query!r}")
    print(f"Repeats per variant: {args.repeats}")
    print(f"Pause between requests: {args.pause}s")
    print(f"Use sessions: {args.use_sessions}")
    if args.use_sessions:
        print(f"Sessions dir: {args.sessions_dir}")

    results: list[VariantResult] = []
    for name, runner, proxy_kind in VARIANTS:
        if not keep(name):
            continue
        r = await bench_variant(
            name,
            runner,
            proxy_kind,
            args.query,
            args.repeats,
            args.pause,
            use_sessions=args.use_sessions,
            sessions_dir=args.sessions_dir,
        )
        results.append(r)

    print_grand_summary(results)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "name": r.name,
                        "runs": [
                            {
                                "ok": run.ok,
                                "seconds": run.seconds,
                                "organic_count": run.organic_count,
                                "error": run.error,
                            }
                            for run in r.runs
                        ],
                    }
                    for r in results
                ],
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"\nSaved raw results -> {args.save}")


if __name__ == "__main__":
    asyncio.run(main())
