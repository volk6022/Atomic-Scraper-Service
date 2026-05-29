"""Batch runner: v2.1 research over all filtered orgs, asyncio.Semaphore(3).

Reads `data/organizations_filtered.json`, runs `simple_agent_v2.run_agent` per
org, saves each result to `data/research/{oid}.json`. Idempotent — skips orgs
that already have a result file (unless OVERWRITE=1).

Usage:
    MODEL=local CONCURRENCY=3 uv run python yandex_enrichment_experiment/03_research_all.py

Env knobs:
    MODEL          local|openrouter-qwen|openrouter-deepseek (default: local)
    CONCURRENCY    int (default: 3 — matches llama-server -np 3)
    LIMIT          int (cap orgs for smoke runs)
    OFFSET         int (skip first N orgs)
    OVERWRITE      1 = re-run already-done orgs
    PICK_INDICES   comma-separated indices (e.g. "0,5,10"), overrides limit/offset
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
FILTERED_PATH = DATA_DIR / "organizations_filtered.json"
RESEARCH_DIR = DATA_DIR / "research"

# Import simple_agent_v2 module directly (filename starts with neither a digit
# nor leading underscore — already valid; just use importlib for robustness).
_agent_spec = importlib.util.spec_from_file_location(
    "simple_agent_v2", str(HERE / "simple_agent_v2.py")
)
assert _agent_spec is not None and _agent_spec.loader is not None
agent_mod = importlib.util.module_from_spec(_agent_spec)
sys.modules["simple_agent_v2"] = agent_mod  # required so dataclass can resolve __module__
_agent_spec.loader.exec_module(agent_mod)


def out_path_for(oid: str, model_key: str) -> Path:
    return RESEARCH_DIR / f"{oid}__{model_key}.json"


async def run_one(org: dict, *, model_key: str, sem: asyncio.Semaphore,
                  progress: dict, total: int, overwrite: bool) -> dict:
    oid = str(org.get("oid"))
    title = (org.get("title") or "")[:60]
    out_path = out_path_for(oid, model_key)
    if out_path.exists() and not overwrite:
        progress["skipped"] += 1
        progress["done"] += 1
        n = progress["done"]
        print(f"  [{n:3d}/{total}] SKIP cached: {title!r} ({oid})", flush=True)
        return {"oid": oid, "status": "cached"}

    async with sem:
        t0 = time.time()
        print(f"  [...] START {title!r} ({oid})", flush=True)
        try:
            result = await agent_mod.run_agent(model_key, oid)
        except Exception as e:
            progress["errors"] += 1
            progress["done"] += 1
            n = progress["done"]
            print(f"  [{n:3d}/{total}] ERROR {title!r} ({oid}): {e!r}"[:200], flush=True)
            return {"oid": oid, "status": "error", "error": repr(e)[:200]}

        try:
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [!!] write fail for {oid}: {e!r}", flush=True)

        progress["done"] += 1
        progress["completed"] += 1
        n = progress["done"]
        elapsed = round(time.time() - t0, 1)
        tk = result.get("tokens", {}).get("grand_total", "?")
        cs = result.get("critic_events", [{}])
        crit_score = cs[0].get("score") if cs else "?"
        print(f"  [{n:3d}/{total}] DONE  {title!r} ({oid}) -> "
              f"{elapsed}s, tok={tk}, critic={crit_score}", flush=True)
        return {"oid": oid, "status": "completed", "elapsed_s": elapsed}


async def main() -> int:
    model_key = os.environ.get("MODEL", "local")
    concurrency = int(os.environ.get("CONCURRENCY", "3"))
    limit = int(os.environ.get("LIMIT", "0")) or None
    offset = int(os.environ.get("OFFSET", "0"))
    overwrite = os.environ.get("OVERWRITE", "0").lower() in ("1", "yes", "true")
    pick_str = os.environ.get("PICK_INDICES", "").strip()

    if not FILTERED_PATH.exists():
        print(f"[!] {FILTERED_PATH} missing — run 02_filter_orgs.py first.")
        return 1
    with FILTERED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    all_kept = data.get("kept_orgs") or []
    print(f"[*] Filtered organizations: {len(all_kept)}")

    if pick_str:
        idxs = sorted({int(x.strip()) for x in pick_str.split(",") if x.strip()})
        organizations = [all_kept[i] for i in idxs if 0 <= i < len(all_kept)]
        print(f"[*] PICK_INDICES={idxs} -> {len(organizations)} orgs")
    else:
        organizations = all_kept[offset:]
        if limit:
            organizations = organizations[:limit]
        print(f"[*] Range: offset={offset}, limit={limit or 'ALL'} -> {len(organizations)} orgs")

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    progress = {"done": 0, "completed": 0, "skipped": 0, "errors": 0}
    total = len(organizations)

    print(f"[*] Model: {model_key}, concurrency: {concurrency}")
    print(f"[*] Output dir: {RESEARCH_DIR}")
    print(f"[*] Overwrite existing: {overwrite}")
    print()
    started = time.time()

    await asyncio.gather(*[
        run_one(o, model_key=model_key, sem=sem, progress=progress,
                total=total, overwrite=overwrite)
        for o in organizations
    ])

    total_elapsed = round(time.time() - started, 1)
    print()
    print(f"[+] Done in {total_elapsed}s "
          f"({round(total_elapsed/max(1, total), 1)}s/org avg).")
    print(f"[+] completed={progress['completed']}, cached={progress['skipped']}, errors={progress['errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
