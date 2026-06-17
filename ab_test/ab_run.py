"""E3: строгий парный A/B на эндпоинте.

Arm A (control): текущий build_query (без prefill, без отзывов).
Arm B (treatment): build_query + блок «ИЗВЕСТНЫЕ ДАННЫЕ из Я.Карточки (как факт)»
                   + блок отзывов (из ab_test/context/{oid}.json).

Оба арма — фикснутый агент + динамическая схема (build_org_card_schema).
Парно по каждой орг → results_A/{oid}.json, results_B/{oid}.json. Идемпотентно.

ENV: ARM=A|B|both (default both), MODE=balanced|quality (default balanced), LIMIT=N
Запуск (GPU): PYTHONIOENCODING=utf-8 python ab_test/ab_run.py
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
API = "http://localhost:8000"
KEY = "default_internal_key"
MODE = os.getenv("MODE", "balanced")
POLL_S, POLL_MAX = 20, 1800

spec = importlib.util.spec_from_file_location(
    "rc", REPO / "yandex_enrichment_experiment" / "02_research_orgs.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def prefill_block(ctx: dict) -> str:
    card = ctx.get("card") or {}
    parts = ["\n\n=== ИЗВЕСТНЫЕ ДАННЫЕ ИЗ КАРТОЧКИ ЯНДЕКС.КАРТ ===",
             "(приняты как ФАКТ — НЕ перепроверяй и НЕ ищи их заново; обязательно "
             "включи в итоговую карточку как есть)"]
    soc = card.get("social_links") or []
    if soc:
        parts.append("Соцсети: " + "; ".join(
            f"{s.get('type')}: {s.get('href')}" for s in soc))
    if card.get("description"):
        parts.append("Описание (Я.Карты): " + str(card["description"])[:400])
    if card.get("phones"):
        parts.append("Телефоны: " + ", ".join(card["phones"]))
    if card.get("hours"):
        parts.append("Часы: " + str(card["hours"])[:120])
    if card.get("rating"):
        parts.append(f"Рейтинг: {card.get('rating')} ({card.get('reviews_count')} отзывов)")
    revs = ctx.get("reviews") or []
    if revs:
        parts.append("\nОТЗЫВЫ КЛИЕНТОВ (последние 6 мес, для what_they_do и "
                     "problems_signals):")
        for r in revs[:12]:
            parts.append(f"- [{r.get('rating')}* {r.get('date')}] {r.get('text')}")
    parts.append("\nЗАДАЧА: не трать запросы на уже известное выше. ДОПОЛНИ карточку "
                 "тем, чего здесь НЕТ (доп. соцсети/сайты, вакансии, масштаб, email).")
    return "\n".join(parts)


def build_query(org, ctx, arm):
    base = rc.build_query(org)
    if arm == "B" and ctx:
        return base + prefill_block(ctx)
    return base


def run_one(http, org, schema, query):
    t0 = time.time()
    r = http.post(f"{API}/api/v1/research/run",
                  headers={"X-API-Key": KEY}, json={"query": query, "mode": MODE,
                  "language": "ru", "output_schema": schema}, timeout=30)
    if r.status_code not in (200, 202):
        return {"status": "run_failed", "code": r.status_code, "body": r.text[:200]}
    tid = r.json().get("task_id")
    el = 0
    while el < POLL_MAX:
        time.sleep(POLL_S); el += POLL_S
        try:
            s = http.get(f"{API}/api/v1/research/status/{tid}", headers={"X-API-Key": KEY}, timeout=15)
        except Exception:
            continue
        if s.status_code != 200:
            return {"status": "status_error", "code": s.status_code}
        p = s.json()
        if p.get("status") in ("completed", "failed"):
            return {"status": p.get("status"), "elapsed_s": round(time.time()-t0, 1), **p}
    return {"status": "timeout"}


def main():
    arm_env = os.getenv("ARM", "both")
    arms = ["A", "B"] if arm_env == "both" else [arm_env]
    limit = int(os.getenv("LIMIT", "0") or 0)
    sel = json.load((HERE / "ab_orgs.json").open(encoding="utf-8"))
    orgs = sel["orgs"][:limit] if limit else sel["orgs"]
    http = httpx.Client()
    for i, org in enumerate(orgs, 1):
        oid = str(org["oid"])
        ctx_path = HERE / "context" / f"{oid}.json"
        ctx = json.loads(ctx_path.read_text(encoding="utf-8")) if ctx_path.exists() else {}
        schema = rc.build_org_card_schema([c.get("name", "") for c in (org.get("categories") or [])])
        for arm in arms:
            out = HERE / f"results_{arm}" / f"{oid}.json"
            out.parent.mkdir(exist_ok=True)
            if out.exists():
                print(f"[{i}/{len(orgs)}] {oid} arm {arm} cached"); continue
            q = build_query(org, ctx, arm)
            print(f"[{i}/{len(orgs)}] {oid} arm {arm} START ({org.get('title','?')[:24]})", flush=True)
            res = run_one(http, org, schema, q)
            res["oid"] = oid; res["arm"] = arm; res["query_len"] = len(q)
            out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{i}/{len(orgs)}] {oid} arm {arm} -> {res.get('status')} in {res.get('elapsed_s','?')}s", flush=True)


if __name__ == "__main__":
    main()
