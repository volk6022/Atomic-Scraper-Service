"""Параллельный прогон организаций через Research Agent (concurrency=3).

POST /api/v1/research/run → poll /status каждые N секунд до status != "running" → save.

Идемпотентно: пропускает уже сохранённые data/research/{oid}.json.

CONCURRENCY: 3 одновременных задачи через asyncio.Semaphore.
  - TaskIQ worker pool сейчас = 3 worker'а (см. ecosystem.config.js)
  - API MAX_CONCURRENT_RESEARCH_TASKS = 5 (soft cap)
  - Локальный LLM на 30 TOPS — 3 параллельные задачи это близко к LLM-пределу.

ENV:
  LIMIT=N    — обработать только первые N организаций (для smoke/debug)
  CONCURRENCY=N — переопределить степень параллелизма (default 3)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_BASE = "http://localhost:8000"
API_KEY = "default_internal_key"
MODE = "quality"  # speed | balanced | quality

CONCURRENCY = int(os.environ.get("CONCURRENCY", "3"))
POLL_INTERVAL_S = 20
POLL_MAX_S = 1800  # 30 мин на одну орг в quality mode

DATA_DIR = Path(__file__).parent / "data"
ORGS_FILE = DATA_DIR / "organizations_dedup.json"
RESEARCH_DIR = DATA_DIR / "research"
REVIEWS_DIR = DATA_DIR / "reviews"
SUMMARY_FILE = DATA_DIR / "research_summary.json"

LANGUAGE = "ru"  # propagated into /research/run; SearXNG + system prompts use it.


# ---------------------------------------------------------------------------
# ORG_CARD_SCHEMA — caller-defined JSON Schema for `output_schema`.
# Lives here (in the experiment script), NOT in the service, so /research
# stays general. The service receives the schema verbatim and forces the
# LLM to fill it via response_format=json_schema (Phase 1a + 2g).
# ---------------------------------------------------------------------------

ORG_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "what_they_do": {"type": "string"},
        "scale_indicators": {
            "type": "array",
            "items": {"type": "string"},
        },
        "tech_stack": {
            "type": "array",
            "items": {"type": "string"},
        },
        "vacancies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "platform": {
                        "type": "string",
                        "enum": ["hh.ru", "superjob.ru", "career_page", "other"],
                    },
                },
            },
        },
        "social": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "vk":        {"type": "array", "items": {"type": "string"}},
                "telegram":  {"type": "array", "items": {"type": "string"}},
                "instagram": {"type": "array", "items": {"type": "string"}},
                "youtube":   {"type": "array", "items": {"type": "string"}},
                "linkedin":  {"type": "array", "items": {"type": "string"}},
                "habr":      {"type": "array", "items": {"type": "string"}},
            },
        },
        "contacts": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "phones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "number": {"type": "string"},
                            "context": {"type": "string"},
                        },
                    },
                },
                "emails": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "address": {"type": "string"},
                            "context": {"type": "string"},
                        },
                    },
                },
                # multiple websites — plan calls for array, not single string
                "websites": {"type": "array", "items": {"type": "string"}},
            },
        },
        "yandex_maps": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rating":         {"type": "number"},
                "reviews_count":  {"type": "integer"},
                "reviews_sample": {"type": "array", "items": {"type": "string"}},
                "hours":          {"type": "string"},
            },
        },
        "problems_signals": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "what_it_provided": {"type": "string"},
                },
            },
        },
    },
}


# Категории, для которых tech_stack осмыслен. Для остальных (кафе, пекарни,
# салоны…) поле убираем из схемы — анализ 517 показал schema_gap у 141 орг
# (tech_stack массово пуст и нерелевантен).
TECH_CATEGORY_HINTS = (
    "it", "айти", "разработк", "программн", "софт", "software", "веб", "web",
    "digital", "диджитал", "интернет", "телеком", "хостинг", "стартап",
    "маркетинг", "реклам", "агентств", "студия", "дизайн", "сайт", "приложен",
    "data", "ai", "ml", "saas", "кибербез", "интегратор", "1с", "crm",
)


def build_org_card_schema(categories: list[str]) -> dict:
    """Схема карточки под конкретную орг: tech_stack только для tech/digital."""
    import copy
    schema = copy.deepcopy(ORG_CARD_SCHEMA)
    cats = " ".join(str(c) for c in (categories or [])).lower()
    if not any(h in cats for h in TECH_CATEGORY_HINTS):
        schema["properties"].pop("tech_stack", None)
    return schema


def load_reviews_snippets(oid: str, max_snippets: int = 8) -> list[str]:
    """Return up to N short review texts from cached data/reviews/{oid}.json.

    Returns [] if no file exists or it was a low-count sentinel — callers
    treat absence as "no extra signal".
    """
    if not oid:
        return []
    path = REVIEWS_DIR / f"{oid}.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []
    if payload.get("skipped_low_count") or payload.get("error"):
        return []
    reviews = payload.get("reviews") or []
    snippets: list[str] = []
    for r in reviews[:max_snippets * 2]:
        text = (r.get("text") or r.get("review_text") or "").strip()
        if not text:
            continue
        # keep snippets compact — the LLM doesn't need more than ~300 chars per review
        snippets.append(text[:300])
        if len(snippets) >= max_snippets:
            break
    return snippets


def build_query(org: dict[str, Any]) -> str:
    """Generic resume-INDEPENDENT enrichment query.

    Asks the research agent to collect what we'd otherwise have to scrape by
    hand: sites, socials, vacancies, contacts, Yandex.Maps card. The schema
    (ORG_CARD_SCHEMA) is what forces the LLM to fill specific fields; this
    query just provides org context + the known review signal.
    """
    title = org.get("title", "")
    cats_list = [c.get("name", "") for c in (org.get("categories") or [])]
    cats = ", ".join(c for c in cats_list if c)[:200]
    site = org.get("site") or ""
    addr = org.get("address") or org.get("fullAddress") or org.get("full_address") or ""
    rating = org.get("rating")
    reviews_count = org.get("reviewsCount") or 0
    oid = org.get("oid")

    parts = [f"Организация: {title}"]
    if cats:
        parts.append(f"категории: {cats}")
    if addr:
        parts.append(f"адрес: {addr}")
    if site:
        parts.append(f"сайт (из Я.Карт): {site}")
    if rating is not None:
        parts.append(f"рейтинг Я.Карт: {rating} ({reviews_count} отзывов)")

    context = ". ".join(parts)

    review_snippets = load_reviews_snippets(oid)
    reviews_block = ""
    if review_snippets:
        reviews_block = (
            "\n\nИзвестные отзывы с Яндекс.Карт (для понимания специфики и проблем):\n"
            + "\n".join(f"- {s}" for s in review_snippets)
        )

    cats_lower = cats.lower()
    tech_line = ""
    if any(h in cats_lower for h in TECH_CATEGORY_HINTS):
        tech_line = "- используемые технологии / стек (только если это IT/digital-компания)\n"

    return (
        f"{context}.\n\n"
        f"Собери карточку организации. ПРИОРИТЕТ — найти канал для связи в соцсетях, "
        f"т.к. основной способ выхода на такие организации это личное сообщение (DM) "
        f"в соцсети, а не email и не звонок.\n\n"
        f"Найди:\n"
        f"- СОЦСЕТИ организации (VK, Telegram, Instagram, в т.ч. ссылку на активный "
        f"профиль/группу и @-хэндл/ник для DM). Это самое важное.\n"
        f"- что компания делает (короткое описание услуг/продуктов)\n"
        f"- все сайты компании (основной + лендинги + проектные)\n"
        f"- контакты: email (с контекстом — отдел/роль) и телефоны; помечай, если "
        f"телефон мобильный\n"
        f"- индикаторы масштаба (число локаций/филиалов, сотрудников, оборот, если есть)\n"
        f"- открытые вакансии (hh.ru, superjob.ru, карьерные страницы)\n"
        f"{tech_line}"
        f"- сигналы проблем (жалобы клиентов из отзывов, ручные процессы, pain points)\n\n"
        f"Используй карточку Я.Карт и отзывы как первичный источник, дальше иди по "
        f"сайтам и СОЦСЕТЯМ — обязательно открой найденные соцсети скрейпом, чтобы "
        f"достать контактные данные/хэндл. Не выдумывай — если поля нет, оставь пустым."
        f"{reviews_block}"
    )


async def run_research(client: httpx.AsyncClient, query: str,
                       output_schema: dict | None = None) -> str | None:
    """Запустить задачу, вернуть task_id или None при ошибке.

    Передаём ``language="ru"`` и ``output_schema=ORG_CARD_SCHEMA`` — это
    переключает /research в structured-output режим (Phase 4): answer_node
    заполнит ORG_CARD_SCHEMA через response_format=json_schema, а не выдаст
    свободный markdown.
    """
    try:
        resp = await client.post(
            f"{API_BASE}/api/v1/research/run",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={
                "query": query,
                "mode": MODE,
                "language": LANGUAGE,
                "output_schema": output_schema if output_schema is not None else ORG_CARD_SCHEMA,
            },
            timeout=30.0,
        )
    except Exception as e:
        print(f"    ! run error: {e}")
        return None
    if resp.status_code not in (200, 202):
        print(f"    ! run failed: {resp.status_code} {resp.text[:200]}")
        return None
    return resp.json().get("task_id")


async def poll_status(client: httpx.AsyncClient, task_id: str) -> dict[str, Any] | None:
    """Опрашивать /status пока status в running, вернуть финальный payload."""
    elapsed = 0
    while elapsed < POLL_MAX_S:
        try:
            resp = await client.get(
                f"{API_BASE}/api/v1/research/status/{task_id}",
                headers={"X-API-Key": API_KEY},
                timeout=15.0,
            )
        except Exception as e:
            print(f"    ! status poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S
            continue

        if resp.status_code != 200:
            print(f"    ! status {resp.status_code}: {resp.text[:150]}")
            return None

        payload = resp.json()
        status = payload.get("status")
        if status == "completed":
            return payload
        if status == "failed":
            print(f"    ! task failed: {payload.get('progress') or payload}")
            return payload

        await asyncio.sleep(POLL_INTERVAL_S)
        elapsed += POLL_INTERVAL_S

    print(f"    ! timeout after {POLL_MAX_S}s")
    return None


async def process_org(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    idx: int,
    total: int,
    org: dict[str, Any],
    summary_lock: asyncio.Lock,
    summary: list[dict[str, Any]],
) -> None:
    oid = org.get("oid")
    title = org.get("title", "?")[:50]
    out_path = RESEARCH_DIR / f"{oid}.json"

    if out_path.exists():
        try:
            with out_path.open("r", encoding="utf-8") as f:
                cached_status = json.load(f).get("status")
        except Exception:
            cached_status = "unknown"
        async with summary_lock:
            summary.append({"oid": oid, "title": title, "cached": True, "status": cached_status})
        return

    async with sem:
        print(f"[{idx:3d}/{total}] start {title!r}", flush=True)
        t0 = time.time()

        query = build_query(org)
        org_cats = [c.get("name", "") for c in (org.get("categories") or [])]
        schema = build_org_card_schema(org_cats)
        task_id = await run_research(client, query, output_schema=schema)
        if not task_id:
            return

        result = await poll_status(client, task_id)
        elapsed = time.time() - t0

        if result is None:
            payload = {"oid": oid, "title": title, "status": "timeout",
                       "task_id": task_id, "query": query}
        else:
            payload = {"oid": oid, "title": title,
                       "task_id": task_id, "query": query,
                       "elapsed_s": round(elapsed, 1),
                       **result}

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        status_short = payload.get("status", "?")
        print(f"[{idx:3d}/{total}] done  {title!r} -> {status_short} in {elapsed:.0f}s", flush=True)

        async with summary_lock:
            summary.append({"oid": oid, "title": title, "status": status_short,
                            "elapsed_s": round(elapsed, 1)})
            with SUMMARY_FILE.open("w", encoding="utf-8") as f:
                json.dump({
                    "processed": len(summary),
                    "total": total,
                    "concurrency": CONCURRENCY,
                    "items": summary,
                }, f, ensure_ascii=False, indent=2)


async def amain() -> int:
    if not ORGS_FILE.exists():
        print(f"[-] {ORGS_FILE} not found. Run 01_scrape_yandex.py first.")
        return 1

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    with ORGS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    orgs = data.get("organizations", [])

    pick_env = os.environ.get("PICK_INDICES")
    if pick_env:
        # comma-separated 0-indexed positions into organizations_dedup.json
        try:
            picks = [int(p.strip()) for p in pick_env.split(",") if p.strip()]
            orgs = [orgs[i] for i in picks if 0 <= i < len(orgs)]
            print(f"[*] PICK_INDICES={picks} applied -> {len(orgs)} orgs")
        except ValueError:
            print(f"[!] PICK_INDICES malformed: {pick_env!r} — ignoring")
    else:
        offset_env = os.environ.get("OFFSET")
        if offset_env:
            try:
                offset = int(offset_env)
                orgs = orgs[offset:]
                print(f"[*] OFFSET={offset} applied")
            except ValueError:
                pass

        limit_env = os.environ.get("LIMIT")
        if limit_env:
            try:
                limit = int(limit_env)
                orgs = orgs[:limit]
                print(f"[*] LIMIT={limit} applied")
            except ValueError:
                pass

    print(f"[*] Loaded {len(orgs)} organizations.")
    print(f"[*] Mode: {MODE}, concurrency: {CONCURRENCY}, poll interval: {POLL_INTERVAL_S}s")
    print()

    sem = asyncio.Semaphore(CONCURRENCY)
    summary: list[dict[str, Any]] = []
    summary_lock = asyncio.Lock()

    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(
            *[process_org(client, sem, i, len(orgs), o, summary_lock, summary)
              for i, o in enumerate(orgs, 1)]
        )

    print()
    cached = sum(1 for it in summary if it.get("cached"))
    print(f"[+] Done. Processed: {len(summary) - cached}, cached/skipped: {cached}")
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
