"""Simple 2-tool LLM agent for the Агат comparison.

No LangGraph, no multi-node pipeline. Just an agent loop:
  - tool: web_serp(query, k)   → list of {url,title,snippet}
  - tool: web_scrape(url)      → page text (httpx, no JS)
  - tool: submit_org_card(card)→ terminal — final structured output

The model decides itself when to search, when to scrape, when to submit.
Uses tool_choice="auto" so all 3 OpenAI-compatible models work uniformly.

Usage:
    MODEL=local|openrouter-qwen|openrouter-deepseek uv run python simple_agent.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- model presets ----------------------------------------------------------

OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")

MODELS = {
    "local": {
        "base_url": "http://localhost:20022/v1/",
        "api_key": "lm-studio",
        "model": "qwen3.5-9b-claude-4.6-opus-reasoning-distilled",
    },
    "openrouter-qwen": {
        "base_url": "https://openrouter.ai/api/v1/",
        "api_key": OPENROUTER_KEY,
        "model": "qwen/qwen3.5-plus-20260420",
    },
    "openrouter-deepseek": {
        "base_url": "https://openrouter.ai/api/v1/",
        "api_key": OPENROUTER_KEY,
        "model": "deepseek/deepseek-v4-flash",
    },
}

SEARXNG_URL = "http://localhost:8080/search"
SEARXNG_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# --- target query (verbatim from baseline pipeline) ------------------------

AGAT_QUERY = """Организация: Агат. категории: Адвокаты, юридические услуги. адрес: 6-я Красноармейская ул., 3. рейтинг Я.Карт: 4.699999809265137 (110 отзывов).

Собери карточку организации. Найди:
- что компания делает (короткое описание услуг/продуктов)
- индикаторы масштаба (число локаций, сотрудников, годовой оборот, если есть)
- используемые технологии / стек (если упоминаются)
- открытые вакансии (hh.ru, superjob.ru, карьерные страницы)
- соцсети (VK, Telegram, Instagram, YouTube, LinkedIn, Habr)
- контакты (телефоны и email с контекстом — отдел / роль)
- все сайты компании (основной + лендинги + проектные)
- сигналы проблем (жалобы клиентов, ручные процессы, упоминаемые pain points)

Используй карточку Я.Карт и отзывы как первичный источник, дальше иди по сайтам и соцсетям. Не выдумывай данные — если поля нет, оставь пустым.

ВНИМАНИЕ: есть несвязанная московская «Юридическая компания Агат» (Yell.ru). Не смешивай их.
"""

ORG_CARD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "what_they_do": {"type": "string"},
        "scale_indicators": {"type": "array", "items": {"type": "string"}},
        "tech_stack": {"type": "array", "items": {"type": "string"}},
        "vacancies": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "title": {"type": "string"}, "url": {"type": "string"},
            "platform": {"type": "string", "enum": ["hh.ru", "superjob.ru", "career_page", "other"]},
        }}},
        "social": {"type": "object", "additionalProperties": False, "properties": {
            "vk": {"type": "array", "items": {"type": "string"}},
            "telegram": {"type": "array", "items": {"type": "string"}},
            "instagram": {"type": "array", "items": {"type": "string"}},
            "youtube": {"type": "array", "items": {"type": "string"}},
            "linkedin": {"type": "array", "items": {"type": "string"}},
            "habr": {"type": "array", "items": {"type": "string"}},
        }},
        "contacts": {"type": "object", "additionalProperties": False, "properties": {
            "phones": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
                "number": {"type": "string"}, "context": {"type": "string"}}}},
            "emails": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
                "address": {"type": "string"}, "context": {"type": "string"}}}},
            "websites": {"type": "array", "items": {"type": "string"}},
        }},
        "yandex_maps": {"type": "object", "additionalProperties": False, "properties": {
            "rating": {"type": "number"}, "reviews_count": {"type": "integer"},
            "reviews_sample": {"type": "array", "items": {"type": "string"}},
            "hours": {"type": "string"},
        }},
        "problems_signals": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "url": {"type": "string"}, "what_it_provided": {"type": "string"}}}},
    },
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_serp",
            "description": "Search the web via SearXNG. Returns up to k results with url/title/snippet.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Search query (Russian or English)."},
                    "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_scrape",
            "description": "Fetch a URL and return cleaned plaintext (max 8 KB). Use after web_serp to read a page.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url"],
                "properties": {"url": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_org_card",
            "description": (
                "Submit the final org card. Call this ONCE when you have enough information. "
                "Pass the ORG_CARD object as `card`. Empty/null fields are fine — DO NOT hallucinate."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["card"],
                "properties": {"card": ORG_CARD_SCHEMA},
            },
        },
    },
]

SYSTEM_PROMPT = """You are a research agent. Your job is to research a single organization and submit a structured org card.

You have three tools:
- web_serp(query, k): SERP via SearXNG. Use short queries (≤5 Russian/English words). Prefer specific domain hints (vk.com, hh.ru, 2gis.ru) when possible.
- web_scrape(url): fetch a URL and return text. Use after web_serp.
- submit_org_card(card): terminal — submits the final card and ends the task.

Process:
1. Read the user's task.
2. Search and scrape iteratively (4-12 calls is normal).
3. When you have enough verified info, call submit_org_card EXACTLY ONCE.

Rules:
- DO NOT hallucinate. Use only data you actually retrieved.
- DO NOT mix the target entity with similarly-named different ones. Verify entity identity from the Yandex.Maps card link or from the address.
- Empty fields → empty array / empty string. Null is fine.
- Russian text in Russian; English in English.

When you are ready, call submit_org_card — DO NOT just write JSON in your reply."""


# --- tool implementations ---------------------------------------------------

@dataclass
class TraceEntry:
    turn: int
    role: str
    content: str = ""
    tool_calls: list = field(default_factory=list)
    tool_call_id: str = ""
    tool_name: str = ""
    elapsed_s: float = 0.0


async def tool_web_serp(client: httpx.AsyncClient, query: str, k: int = 5) -> dict:
    try:
        r = await client.get(
            SEARXNG_URL,
            params={"q": query, "format": "json", "language": "ru"},
            headers=SEARXNG_HEADERS,
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        seen = set()
        for item in (data.get("results") or []):
            link = item.get("url") or ""
            if not link.startswith("http") or link in seen:
                continue
            seen.add(link)
            results.append({
                "url": link,
                "title": (item.get("title") or "").strip(),
                "snippet": (item.get("content") or "").strip()[:300],
            })
            if len(results) >= k:
                break
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"query": query, "error": str(e)[:200], "results": []}


async def tool_web_scrape(client: httpx.AsyncClient, url: str) -> dict:
    try:
        r = await client.get(url, timeout=15.0, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        if r.status_code >= 400:
            return {"url": url, "error": f"http {r.status_code}", "text": ""}
        # Crude HTML→text: strip tags & scripts
        import re
        body = r.text
        body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        return {"url": url, "text": body[:8000], "length": len(body)}
    except Exception as e:
        return {"url": url, "error": str(e)[:200], "text": ""}


# --- agent loop -------------------------------------------------------------

async def run_agent(model_key: str, max_turns: int = 25) -> dict:
    cfg = MODELS[model_key]
    client = AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"],
                         timeout=httpx.Timeout(180.0, connect=10.0), max_retries=2)
    http = httpx.AsyncClient()

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": AGAT_QUERY},
    ]
    trace: list[dict] = []
    submitted_card: dict | None = None
    started = time.time()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    tool_call_count = {"web_serp": 0, "web_scrape": 0, "submit_org_card": 0}

    for turn in range(1, max_turns + 1):
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=cfg["model"], messages=messages, tools=TOOLS, tool_choice="auto",
            )
        except Exception as e:
            trace.append({"turn": turn, "role": "error", "content": f"LLM call failed: {e!r}"})
            break
        elapsed = time.time() - t0

        usage = getattr(resp, "usage", None)
        if usage:
            total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        msg = resp.choices[0].message
        tcs = getattr(msg, "tool_calls", None) or []

        # Record assistant turn (must include tool_calls if any, for next-turn context)
        asst_record = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if tcs:
            asst_record["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ]
        messages.append(asst_record)
        trace.append({
            "turn": turn, "role": "assistant",
            "content": (msg.content or "")[:1000],
            "tool_calls": [{"name": tc.function.name, "args": tc.function.arguments[:500]} for tc in tcs],
            "elapsed_s": round(elapsed, 2),
        })

        if not tcs:
            # No tools, no submit — model just talked. Probably done or stuck.
            trace.append({"turn": turn, "role": "note", "content": "Model did not call any tool — stopping."})
            break

        # Execute each tool call
        for tc in tcs:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_call_count[name] = tool_call_count.get(name, 0) + 1
            tt = time.time()
            if name == "web_serp":
                result = await tool_web_serp(http, args.get("query", ""), args.get("k", 5))
            elif name == "web_scrape":
                result = await tool_web_scrape(http, args.get("url", ""))
            elif name == "submit_org_card":
                submitted_card = args.get("card") or args  # some models flatten
                result = {"submitted": True}
            else:
                result = {"error": f"unknown tool {name}"}

            t_elapsed = time.time() - tt
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": name,
                "content": json.dumps(result, ensure_ascii=False)[:6000],
            })
            trace.append({
                "turn": turn, "role": "tool", "tool_name": name,
                "args": json.dumps(args, ensure_ascii=False)[:300],
                "result_preview": json.dumps(result, ensure_ascii=False)[:400],
                "elapsed_s": round(t_elapsed, 2),
            })

        if submitted_card is not None:
            break

    await http.aclose()
    total_elapsed = time.time() - started
    return {
        "model": model_key,
        "model_id": cfg["model"],
        "elapsed_s": round(total_elapsed, 1),
        "turns": len([t for t in trace if t["role"] == "assistant"]),
        "tool_call_counts": tool_call_count,
        "tokens": {"prompt": total_prompt_tokens, "completion": total_completion_tokens,
                   "total": total_prompt_tokens + total_completion_tokens},
        "submitted_card": submitted_card,
        "trace": trace,
    }


# --- runner -----------------------------------------------------------------

async def main() -> int:
    model_key = os.environ.get("MODEL", "local")
    if model_key not in MODELS:
        print(f"Unknown MODEL={model_key}. Options: {list(MODELS)}")
        return 2

    out_dir = Path(__file__).parent / "data" / "research_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"agat__SIMPLE_{model_key}.json"

    print(f"[*] Running simple-agent on model={model_key} ({MODELS[model_key]['model']})")
    print(f"[*] Target: Агат, output → {out_path.name}")
    result = await run_agent(model_key)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[+] Done in {result['elapsed_s']}s, turns={result['turns']}, "
          f"calls={result['tool_call_counts']}, tokens={result['tokens']}")
    print(f"[+] Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
