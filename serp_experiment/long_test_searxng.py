"""Длинный стресс-тест SearXNG: 10 query x 10 repeats = 100 запросов.

Запускать через uv из корня репо:

    uv run python -u -m serp_experiment.long_test_searxng

Дополнительно:
    --repeats N            # сколько повторов на каждый query (default 10)
    --pause-req S          # пауза между запросами одного query (default 2.0)
    --pause-query S        # пауза между разными query (default 4.0)
    --save PATH            # куда писать сырые тайминги
                             (default: serp_experiment/results_searxng_long.json)
    --base-url URL         # base url SearXNG (default http://localhost:8080)

Что сохраняется в JSON:
    [
        { "query": "...",
          "runs": [{ok, seconds, organic_count, error}, ...] },
        ...
    ]

Что печатается в stdout:
    - на каждый запрос:  [q3 4/10] OK 3.21s organic=10
    - в конце каждого query: per-query summary
    - в конце всего: grand summary (success-rate, mean/median/p95)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approaches import searxng_local


# 10 разнотипных query — чтобы апстримы не отдавали одни и те же кэши и
# чтобы покрыть разные категории (factual, local, commercial, технические,
# свежие новости и т.п.).
DEFAULT_QUERIES: list[str] = [
    "What is artificial intelligence",
    "python asyncio tutorial",
    "best coffee shops Saint Petersburg Russia",
    "how to bake sourdough bread at home",
    "GDP of Germany 2024",
    "Tesla stock price last 5 years",
    "climate change effects 2025",
    "best science fiction movies 2024",
    "buy iPhone 15 Pro Max",
    "weather forecast Moscow tomorrow",
]


@dataclass
class RunResult:
    ok: bool
    seconds: float
    organic_count: int = 0
    error: str = ""


@dataclass
class QueryResult:
    query: str
    runs: list[RunResult] = field(default_factory=list)


async def _fetch(query: str, base_url: str) -> dict[str, Any]:
    return await asyncio.to_thread(
        searxng_local.fetch_serp, query, base_url=base_url
    )


async def run_query(
    qi: int,
    query: str,
    repeats: int,
    pause_req: float,
    base_url: str,
) -> QueryResult:
    print(f"\n=== q{qi}  {query!r} ===")
    res = QueryResult(query=query)

    for i in range(1, repeats + 1):
        t0 = time.perf_counter()
        try:
            payload = await _fetch(query, base_url)
            dt = time.perf_counter() - t0
            organic = payload.get("organic", [])
            run = RunResult(ok=bool(organic), seconds=dt, organic_count=len(organic))
            tag = "OK   " if run.ok else "EMPTY"
            print(f"  [q{qi} {i:>2}/{repeats}] {tag} {dt:6.2f}s  organic={run.organic_count}")
        except Exception as e:  # noqa: BLE001
            dt = time.perf_counter() - t0
            run = RunResult(ok=False, seconds=dt, error=f"{type(e).__name__}: {e}")
            print(f"  [q{qi} {i:>2}/{repeats}] FAIL  {dt:6.2f}s  {run.error}")

        res.runs.append(run)
        if i < repeats and pause_req > 0:
            await asyncio.sleep(pause_req)

    _print_query_summary(res)
    return res


def _print_query_summary(r: QueryResult) -> None:
    if not r.runs:
        return
    times = [run.seconds for run in r.runs]
    oks = [run for run in r.runs if run.ok]
    organic = [run.organic_count for run in r.runs if run.ok]
    success_rate = 100.0 * len(oks) / len(r.runs)
    print(
        f"  summary: success={len(oks)}/{len(r.runs)} ({success_rate:.0f}%)  "
        f"mean={statistics.mean(times):.2f}s  median={statistics.median(times):.2f}s  "
        f"avg_organic={statistics.mean(organic) if organic else 0:.1f}"
    )


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(round(0.95 * (len(s) - 1))))
    return s[idx]


def print_grand_summary(results: list[QueryResult]) -> None:
    print("\n" + "=" * 86)
    print("GRAND SUMMARY (long test)")
    print("=" * 86)
    print(
        f"{'query':50s} {'ok':>7s} {'mean':>8s} {'median':>8s} {'p95':>8s} {'organic':>9s}"
    )
    print("-" * 86)

    all_times: list[float] = []
    all_oks: int = 0
    all_runs: int = 0
    all_organic: list[int] = []

    for r in results:
        times = [run.seconds for run in r.runs]
        oks = [run for run in r.runs if run.ok]
        organic = [run.organic_count for run in r.runs if run.ok]
        all_times.extend(times)
        all_oks += len(oks)
        all_runs += len(r.runs)
        all_organic.extend(organic)
        q = r.query if len(r.query) <= 50 else r.query[:47] + "..."
        rate = f"{len(oks)}/{len(r.runs)}"
        print(
            f"{q:50s} {rate:>7s} "
            f"{statistics.mean(times):>7.2f}s "
            f"{statistics.median(times):>7.2f}s "
            f"{_p95(times):>7.2f}s "
            f"{(statistics.mean(organic) if organic else 0):>9.1f}"
        )

    print("-" * 86)
    overall_rate = 100.0 * all_oks / all_runs if all_runs else 0
    print(
        f"{'TOTAL':50s} {f'{all_oks}/{all_runs}':>7s} "
        f"{statistics.mean(all_times):>7.2f}s "
        f"{statistics.median(all_times):>7.2f}s "
        f"{_p95(all_times):>7.2f}s "
        f"{(statistics.mean(all_organic) if all_organic else 0):>9.1f}"
    )
    print(f"\nOverall success rate: {overall_rate:.1f}%  ({all_oks}/{all_runs})")


async def amain() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--pause-req", type=float, default=2.0)
    ap.add_argument("--pause-query", type=float, default=4.0)
    ap.add_argument(
        "--save",
        type=str,
        default=str(
            Path(__file__).resolve().parent / "results_searxng_long.json"
        ),
    )
    ap.add_argument("--base-url", type=str, default="http://localhost:8080")
    args = ap.parse_args()

    queries = DEFAULT_QUERIES
    total = len(queries) * args.repeats
    print(
        f"Long SearXNG test: {len(queries)} queries x {args.repeats} repeats = {total} requests\n"
        f"pause-req={args.pause_req}s  pause-query={args.pause_query}s  base_url={args.base_url}"
    )

    started = time.perf_counter()
    results: list[QueryResult] = []
    for qi, query in enumerate(queries, start=1):
        r = await run_query(qi, query, args.repeats, args.pause_req, args.base_url)
        results.append(r)
        if qi < len(queries) and args.pause_query > 0:
            await asyncio.sleep(args.pause_query)

    elapsed = time.perf_counter() - started
    print_grand_summary(results)
    print(f"\nTotal elapsed: {elapsed:.1f}s")

    # save raw
    save_path = Path(args.save)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(
        json.dumps(
            [
                {
                    "query": r.query,
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
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Saved raw results -> {save_path}")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
