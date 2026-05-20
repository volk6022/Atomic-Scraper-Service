"""Широкий стресс-тест SearXNG: 30 query x 10 repeats = 300 запросов.

Отличия от long_test_searxng.py:
- больше query (30 вместо 10), все разнотипные;
- минимальная пауза между запросами (0.1s);
- ретраи (default 2 — то есть до 3 попыток на каждый logical request);
- ретрай срабатывает и на exception, и на EMPTY-ответ (0 organic).

Запуск:
    uv run python -u -m serp_experiment.wide_test_searxng

CLI:
    --repeats N          # повторов на каждый query (default 10 → 30*10=300)
    --pause-req S        # пауза между запросами одного query (default 0.1)
    --pause-query S      # пауза между разными query (default 0.5)
    --retries N          # сколько ретраев на каждый logical request (default 2)
    --save PATH
    --base-url URL       # default http://localhost:8080
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


DEFAULT_QUERIES: list[str] = [
    # 10 from long_test
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
    # +20 new across categories
    "JavaScript framework comparison 2024",
    "best restaurants in Tokyo Michelin",
    "how to fix WiFi connection issues",
    "history of the Roman Empire",
    "cryptocurrency market analysis today",
    "yoga poses for beginners",
    "top universities in Europe 2024",
    "upcoming Marvel movies 2025",
    "sustainable energy solutions home",
    "chocolate cake recipe easy",
    "best programming languages to learn 2025",
    "Bitcoin price prediction 2025",
    "hiking trails Switzerland Alps",
    "Docker containers tutorial",
    "mortgage rates US 2024",
    "cat behavior explained",
    "best electric cars 2024",
    "symptoms of the common cold",
    "Linux command line basics",
    "photography tips for beginners DSLR",
]


@dataclass
class RunResult:
    ok: bool
    seconds: float
    organic_count: int = 0
    attempts: int = 1
    error: str = ""
    started_at: float = 0.0   # epoch seconds; для post-hoc анализа конкуренции
    repeat_idx: int = 0       # 1-based, в каком порядке запускался внутри query


@dataclass
class QueryResult:
    query: str
    runs: list[RunResult] = field(default_factory=list)


async def _fetch(query: str, base_url: str) -> dict[str, Any]:
    return await asyncio.to_thread(
        searxng_local.fetch_serp, query, base_url=base_url
    )


async def _try_once_with_retries(
    query: str, base_url: str, retries: int
) -> RunResult:
    """Up to `retries + 1` attempts. Stop on first success (organic > 0).

    Returns RunResult with total elapsed across all attempts and attempts count.
    started_at — записывается на старте первой попытки (epoch seconds).
    """
    t0 = time.perf_counter()
    started_at = time.time()
    last_err = ""
    organic_count = 0
    for attempt in range(1, retries + 2):
        try:
            payload = await _fetch(query, base_url)
            organic = payload.get("organic", [])
            organic_count = len(organic)
            if organic_count > 0:
                dt = time.perf_counter() - t0
                return RunResult(
                    ok=True,
                    seconds=dt,
                    organic_count=organic_count,
                    attempts=attempt,
                    started_at=started_at,
                )
            last_err = "empty"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        # without delay between retries — they're already paced by upstream RTT
    dt = time.perf_counter() - t0
    return RunResult(
        ok=False,
        seconds=dt,
        organic_count=organic_count,
        attempts=retries + 1,
        error=last_err,
        started_at=started_at,
    )


async def run_query(
    qi: int,
    query: str,
    repeats: int,
    pause_req: float,
    base_url: str,
    retries: int,
) -> QueryResult:
    """Sequential one-query loop. Используется в concurrency=1 режиме."""
    print(f"\n=== q{qi:>2}  {query!r} ===")
    res = QueryResult(query=query)

    for i in range(1, repeats + 1):
        run = await _try_once_with_retries(query, base_url, retries)
        run.repeat_idx = i
        tag = "OK   " if run.ok else "FAIL "
        att = f"att={run.attempts}"
        org = f"organic={run.organic_count}"
        line = f"  [q{qi:>2} {i:>2}/{repeats}] {tag} {run.seconds:6.2f}s  {att}  {org}"
        if not run.ok and run.error and run.error != "empty":
            line += f"  {run.error}"
        print(line)
        res.runs.append(run)
        if i < repeats and pause_req > 0:
            await asyncio.sleep(pause_req)

    _print_query_summary(res)
    return res


async def run_all_parallel(
    queries: list[str],
    repeats: int,
    pause_req: float,
    base_url: str,
    retries: int,
    concurrency: int,
) -> list[QueryResult]:
    """Параллельный режим: flat-task-list (qi, query, repeat_idx), Semaphore(N).

    Per-request строки печатаются по мере завершения (порядок недетерминирован),
    summary — в конце после группировки по qi.
    """
    sem = asyncio.Semaphore(concurrency)
    # подготавливаем результаты: list[QueryResult] с пустыми runs длины repeats
    qresults: list[QueryResult] = [QueryResult(query=q) for q in queries]
    runs_by_q: list[list[RunResult | None]] = [
        [None] * repeats for _ in queries
    ]

    total = len(queries) * repeats
    done = 0

    async def _one_task(qi0: int, query: str, repeat_idx: int) -> None:
        nonlocal done
        async with sem:
            # лёгкая пауза перед стартом — снимаем burst при первом залпе
            if pause_req > 0:
                await asyncio.sleep(pause_req)
            run = await _try_once_with_retries(query, base_url, retries)
            run.repeat_idx = repeat_idx
            runs_by_q[qi0][repeat_idx - 1] = run
            done += 1
            tag = "OK   " if run.ok else "FAIL "
            att = f"att={run.attempts}"
            org = f"organic={run.organic_count}"
            line = (
                f"  [q{qi0+1:>2} {repeat_idx:>2}/{repeats}] {tag} "
                f"{run.seconds:6.2f}s  {att}  {org}  ({done}/{total})"
            )
            if not run.ok and run.error and run.error != "empty":
                line += f"  {run.error}"
            print(line, flush=True)

    tasks = [
        asyncio.create_task(_one_task(qi0, q, ri))
        for qi0, q in enumerate(queries)
        for ri in range(1, repeats + 1)
    ]
    print(
        f"\n[parallel] {total} tasks, concurrency={concurrency}, pause-req={pause_req}s\n",
        flush=True,
    )
    await asyncio.gather(*tasks, return_exceptions=True)

    # Собираем QueryResult в порядке qi
    for qi0, qr in enumerate(qresults):
        runs = [r for r in runs_by_q[qi0] if r is not None]
        qr.runs = runs
    # Печатаем per-query summary после параллельной фазы
    print("\n----- per-query summary -----")
    for qi0, qr in enumerate(qresults):
        print(f"\n=== q{qi0+1:>2}  {qr.query!r} ===")
        _print_query_summary(qr)

    return qresults


def _print_query_summary(r: QueryResult) -> None:
    if not r.runs:
        return
    times = [run.seconds for run in r.runs]
    oks = [run for run in r.runs if run.ok]
    organic = [run.organic_count for run in r.runs if run.ok]
    attempts = [run.attempts for run in r.runs]
    success_rate = 100.0 * len(oks) / len(r.runs)
    print(
        f"  summary: success={len(oks)}/{len(r.runs)} ({success_rate:.0f}%)  "
        f"mean={statistics.mean(times):.2f}s  median={statistics.median(times):.2f}s  "
        f"avg_organic={statistics.mean(organic) if organic else 0:.1f}  "
        f"avg_attempts={statistics.mean(attempts):.2f}"
    )


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(round(0.95 * (len(s) - 1))))
    return s[idx]


def print_grand_summary(results: list[QueryResult]) -> None:
    print("\n" + "=" * 102)
    print("GRAND SUMMARY (wide test)")
    print("=" * 102)
    print(
        f"{'query':50s} {'ok':>7s} {'mean':>8s} {'median':>8s} {'p95':>8s} "
        f"{'organic':>9s} {'att_avg':>8s}"
    )
    print("-" * 102)

    all_times: list[float] = []
    all_oks: int = 0
    all_runs: int = 0
    all_organic: list[int] = []
    all_attempts: list[int] = []

    for r in results:
        times = [run.seconds for run in r.runs]
        oks = [run for run in r.runs if run.ok]
        organic = [run.organic_count for run in r.runs if run.ok]
        attempts = [run.attempts for run in r.runs]
        all_times.extend(times)
        all_oks += len(oks)
        all_runs += len(r.runs)
        all_organic.extend(organic)
        all_attempts.extend(attempts)
        q = r.query if len(r.query) <= 50 else r.query[:47] + "..."
        rate = f"{len(oks)}/{len(r.runs)}"
        print(
            f"{q:50s} {rate:>7s} "
            f"{statistics.mean(times):>7.2f}s "
            f"{statistics.median(times):>7.2f}s "
            f"{_p95(times):>7.2f}s "
            f"{(statistics.mean(organic) if organic else 0):>9.1f} "
            f"{(statistics.mean(attempts) if attempts else 0):>8.2f}"
        )

    print("-" * 102)
    overall_rate = 100.0 * all_oks / all_runs if all_runs else 0
    print(
        f"{'TOTAL':50s} {f'{all_oks}/{all_runs}':>7s} "
        f"{statistics.mean(all_times):>7.2f}s "
        f"{statistics.median(all_times):>7.2f}s "
        f"{_p95(all_times):>7.2f}s "
        f"{(statistics.mean(all_organic) if all_organic else 0):>9.1f} "
        f"{(statistics.mean(all_attempts) if all_attempts else 0):>8.2f}"
    )
    print(f"\nOverall success rate: {overall_rate:.1f}%  ({all_oks}/{all_runs})")

    # breakdown by attempts
    from collections import Counter
    c = Counter(all_attempts)
    print("Attempts histogram:")
    for k in sorted(c):
        print(f"  attempts={k}:  {c[k]}")


async def amain() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--pause-req", type=float, default=0.1)
    ap.add_argument("--pause-query", type=float, default=0.5)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="параллельность (default 4 = 20%% от пула 20). 1 = sequential.",
    )
    ap.add_argument(
        "--save",
        type=str,
        default=str(
            Path(__file__).resolve().parent / "results_searxng_wide.json"
        ),
    )
    ap.add_argument("--base-url", type=str, default="http://localhost:8080")
    args = ap.parse_args()

    queries = DEFAULT_QUERIES
    total = len(queries) * args.repeats
    print(
        f"Wide SearXNG test: {len(queries)} queries x {args.repeats} repeats = {total} requests\n"
        f"pause-req={args.pause_req}s  pause-query={args.pause_query}s  retries={args.retries}  "
        f"concurrency={args.concurrency}  base_url={args.base_url}"
    )

    started = time.perf_counter()
    if args.concurrency <= 1:
        results: list[QueryResult] = []
        for qi, query in enumerate(queries, start=1):
            r = await run_query(
                qi, query, args.repeats, args.pause_req, args.base_url, args.retries
            )
            results.append(r)
            if qi < len(queries) and args.pause_query > 0:
                await asyncio.sleep(args.pause_query)
    else:
        results = await run_all_parallel(
            queries=queries,
            repeats=args.repeats,
            pause_req=args.pause_req,
            base_url=args.base_url,
            retries=args.retries,
            concurrency=args.concurrency,
        )

    elapsed = time.perf_counter() - started
    print_grand_summary(results)
    print(f"\nTotal elapsed: {elapsed:.1f}s")

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
                            "attempts": run.attempts,
                            "error": run.error,
                            "started_at": run.started_at,
                            "repeat_idx": run.repeat_idx,
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
