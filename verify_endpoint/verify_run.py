"""E2E-прогон выбранных орг через ЭНДПОИНТ /api/v1/research/run.

Использует тот же build_query + ORG_CARD_SCHEMA, что прод-клиент
yandex_enrichment_experiment/02_research_orgs.py — чтобы сравнение с прежними
standalone-картами (simple_agent_v2) было честным.

Идемпотентно: пропускает уже сохранённые verify_endpoint/results/{oid}.json.
Последовательно (одна GPU).

Запуск:
  python verify_endpoint/verify_run.py            # все из selected_orgs.json
  python verify_endpoint/verify_run.py 117327869021   # только указанные oid
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
API_BASE = "http://localhost:8000"
API_KEY = "default_internal_key"
MODE = "quality"
LANGUAGE = "ru"
POLL_S = 20
POLL_MAX_S = 1800

# импортируем build_query + ORG_CARD_SCHEMA из прод-клиента (имя файла с цифрой)
spec = importlib.util.spec_from_file_location(
    "research_client", REPO / "yandex_enrichment_experiment" / "02_research_orgs.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
build_query = client.build_query
ORG_CARD_SCHEMA = client.ORG_CARD_SCHEMA
build_org_card_schema = client.build_org_card_schema


def run_one(http: httpx.Client, org: dict) -> dict:
    oid = str(org.get("oid"))
    query = build_query(org)
    schema = build_org_card_schema([c.get("name", "") for c in (org.get("categories") or [])])
    t0 = time.time()
    r = http.post(f"{API_BASE}/api/v1/research/run",
                  headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                  json={"query": query, "mode": MODE, "language": LANGUAGE,
                        "output_schema": schema}, timeout=30)
    if r.status_code not in (200, 202):
        return {"oid": oid, "status": "run_failed", "code": r.status_code,
                "body": r.text[:300], "query": query}
    task_id = r.json().get("task_id")
    elapsed = 0
    while elapsed < POLL_MAX_S:
        time.sleep(POLL_S); elapsed += POLL_S
        try:
            s = http.get(f"{API_BASE}/api/v1/research/status/{task_id}",
                         headers={"X-API-Key": API_KEY}, timeout=15)
        except Exception as e:
            print(f"    poll err: {e}"); continue
        if s.status_code != 200:
            return {"oid": oid, "status": "status_error", "code": s.status_code,
                    "body": s.text[:300], "task_id": task_id, "query": query}
        payload = s.json()
        st = payload.get("status")
        if st in ("completed", "failed"):
            return {"oid": oid, "status": st, "task_id": task_id,
                    "elapsed_s": round(time.time() - t0, 1), "query": query, **payload}
        print(f"    [{oid}] {st} phase={payload.get('progress',{}).get('phase')} {elapsed}s", flush=True)
    return {"oid": oid, "status": "timeout", "task_id": task_id, "query": query}


def main():
    sel_file = os.getenv("SEL_FILE", "selected_orgs.json")
    sel = json.load((HERE / sel_file).open(encoding="utf-8"))
    orgs = sel["orgs"]
    want = set(sys.argv[1:])
    if want:
        orgs = [o for o in orgs if str(o.get("oid")) in want]
    resdir = HERE / "results"; resdir.mkdir(exist_ok=True)
    for i, org in enumerate(orgs, 1):
        oid = str(org.get("oid"))
        out = resdir / f"{oid}.json"
        if out.exists():
            print(f"[{i}/{len(orgs)}] {oid} cached, skip", flush=True)
            continue
        print(f"[{i}/{len(orgs)}] START {oid} {org.get('title','?')[:30]}", flush=True)
        res = run_one(httpx.Client(), org)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{i}/{len(orgs)}] {oid} -> {res.get('status')} in {res.get('elapsed_s','?')}s", flush=True)


if __name__ == "__main__":
    main()
