"""SIMPLE++ — 2-tool flat agent with cheap context hygiene.

Keeps the simple_agent.py spirit (web_serp / web_scrape / submit_org_card,
tool_choice="auto", model decides) and bolts on six things that cost <2h to
write but eliminate the worst pathologies we saw in baseline simple-agent runs:

  1. auto-compact at 90k prompt_tokens (max 2 hard compactions)
  2. soft-elide old scrape tool_results after 6 turns (no LLM call)
  3. refraser every 4 SERP calls — auxiliary LLM proposes 2-3 new angles,
     injected as `_supervisor_hint` on the next serp result. Model is free
     to use or ignore.
  4. goal-conditioned scrape extract — regex pulls anchor mentions, phones,
     emails, social URLs ±400 chars; falls back to first 2KB if no match.
     Sends only ~2-3KB to the model per scrape instead of 8KB.
  5. domain-failure tracking — after 2 errors on a domain, inject
     `_blocked_domains` into next serp result.
  6. sources sanitization on submit — drop fake/non-URL "sources" entries.

Reuses Агат data from data/organizations.json + data/reviews/{oid}.json.

Usage:
    MODEL=local|openrouter-qwen|openrouter-deepseek \
    OID=226497224828 \
    uv run python simple_agent_v2.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- model presets ---------------------------------------------------------

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

DATA_DIR = Path(__file__).parent / "data"
ORGS_PATH = DATA_DIR / "organizations.json"
REVIEWS_DIR = DATA_DIR / "reviews"
OUT_DIR = DATA_DIR / "research_comparison"

# --- budgets / thresholds --------------------------------------------------

TOKEN_BUDGET = 50_000                  # ≤ 65k slot capacity with 15k margin
MAX_COMPACTIONS = 3                    # bumped — smaller budget → more compactions OK
SOFT_ELIDE_AFTER_TURNS = 4             # aggressive elision under tight budget
REFRASER_EVERY_N_SERPS = 15
DOMAIN_FAIL_THRESHOLD = 3
MAX_TURNS = 25
LLM_TIMEOUT_S = 180.0
SCRAPE_TIMEOUT_S = 15.0
SCRAPE_BUDGET_CHARS = 3500
CRITIC_PASS_SCORE = 8.5                # submit passes only when critic ≥ this
MAX_SUBMIT_REJECTS = 2                 # after N rejections, force-accept to avoid loops
DOMAINS_NEVER_BLOCK = {                # always allowed even after fails (key infra)
    "yandex.ru", "yandex.com", "2gis.ru", "hh.ru", "spb.hh.ru",
    "superjob.ru", "vk.com", "t.me", "telegram.me", "rusprofile.ru",
    "fparf.ru", "checko.ru", "zoon.ru",
}

# --- ORG_CARD_SCHEMA (identical to simple_agent & orch) --------------------

ORG_CARD_SCHEMA: dict[str, Any] = {
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
            "description": "SearXNG search. Use short queries (≤5 words). May include _supervisor_hint or _blocked_domains hints.",
            "parameters": {
                "type": "object", "additionalProperties": False, "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_scrape",
            "description": "Fetch a URL. Returns relevance-filtered extract (~2-3 KB centered on anchor mentions + contact patterns).",
            "parameters": {
                "type": "object", "additionalProperties": False, "required": ["url"],
                "properties": {"url": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_org_card",
            "description": (
                "Terminal: submit final ORG_CARD. A critic LLM evaluates your card before acceptance. "
                "If critic score < 8.5/10 the submit is REJECTED, you get feedback + new angles, and you must continue. "
                "After 2 rejections the next submit is force-accepted. Each source.url must be a URL you actually fetched."
            ),
            "parameters": {
                "type": "object", "additionalProperties": False, "required": ["card"],
                "properties": {"card": ORG_CARD_SCHEMA},
            },
        },
    },
]

# --- target loading (mirrors orchestrator_agent.py) ------------------------

def load_target(oid: str) -> dict:
    with ORGS_PATH.open(encoding="utf-8") as f:
        all_orgs = json.load(f)["organizations"]
    org = next((o for o in all_orgs if str(o.get("oid")) == oid), None)
    if org is None:
        raise SystemExit(f"oid {oid} not found in {ORGS_PATH}")
    reviews: list[dict] = []
    rev_path = REVIEWS_DIR / f"{oid}.json"
    if rev_path.exists():
        with rev_path.open(encoding="utf-8") as f:
            data = json.load(f)
        reviews = data.get("reviews") or []
    return {"org": org, "reviews": reviews}


def build_anchor(org: dict) -> dict:
    cats = [c.get("name") for c in (org.get("categories") or []) if c.get("name")]
    phones = [p.get("number") for p in (org.get("phones") or []) if p.get("number")]
    return {
        "name": org.get("title") or org.get("seoname"),
        "oid": str(org.get("oid")),
        "address": org.get("fullAddress") or org.get("address"),
        "city": "Санкт-Петербург",
        "categories": cats[:3],
        "yandex_phones": phones,
        "yandex_site": org.get("site"),
        "yandex_url": f"https://yandex.ru/maps/org/{org.get('seoname') or ''}/{org.get('oid')}",
    }


def build_user_message(target: dict) -> str:
    org = target["org"]
    reviews = target["reviews"]
    anchor = build_anchor(org)
    cats = ", ".join(anchor["categories"]) or "—"
    phones = ", ".join(anchor["yandex_phones"]) or "—"
    rev_snippets = []
    for r in reviews[:8]:
        txt = (r.get("text") or "").strip().replace("\n", " ")
        if not txt:
            continue
        rev_snippets.append(f"- ({r.get('rating', '?')}/5) {txt[:280]}")
    rev_block = "\n".join(rev_snippets) if rev_snippets else "(нет отзывов с текстом)"
    return f"""Цель: собрать карточку организации (ORG_CARD_SCHEMA).

ANCHOR (целевая организация, ground truth):
- name: {anchor['name']}
- oid (yandex): {anchor['oid']}
- адрес: {anchor['address']}
- город: {anchor['city']}
- категории: {cats}
- телефоны (yandex card): {phones}
- yandex.maps URL: {anchor['yandex_url']}
- сайт из yandex card: {anchor['yandex_site'] or 'не указан'}

Рейтинг yandex.maps: {org.get('rating', '—')} ({org.get('reviewsCount', 0)} отзывов).

Отзывы (top {len(rev_snippets)}):
{rev_block}

Заполни yandex_maps секцию из данных выше. Остальное — собирай из веба.
ВАЖНО: anchor.address и anchor.phones — единственный источник истины об идентичности.
При несовпадении города/адреса/телефона — это ДРУГАЯ организация.
"""

SYSTEM_PROMPT = """You are a research agent. Submit an ORG_CARD for the given organization.

Tools:
- web_serp(query, k): SearXNG search. Use short queries (≤5 Russian words). Tool result may carry hints:
    _supervisor_hint: "..."   — a periodic suggestion of new angles you may not have considered.
    _blocked_domains: [...]   — domains that failed twice; avoid them.
- web_scrape(url): fetch URL, returns ~2-3KB extract focused on the anchor + contact patterns.
- submit_org_card(card): terminal — submit final card.

Rules:
- ANCHOR is ground truth. Different city / address / phone → different entity → discard.
- yandex_maps section: copy rating / reviews_count / reviews_sample from the user message; don't refetch.
- Sources: every source.url MUST be a URL you actually fetched via web_scrape. Do not include tool names or invented URLs.
- Russian text in Russian. No hallucination — empty fields are fine.
- 4-12 tool calls is normal. Call submit_org_card when you believe the card is solid.
- A critic LLM scores your card on submit; if < 8.5/10 the submit is rejected and you get specific feedback to address. Use the feedback, don't redo from scratch.
- _supervisor_hint may appear in serp results; treat as optional suggestions, not mandates.
"""

# --- HTML→text + goal-conditioned extract ---------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PHONE_RE = re.compile(r"\+?7[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SOCIAL_RE = re.compile(r"(?:vk\.com|t\.me|telegram\.me|instagram\.com|youtube\.com|linkedin\.com|habr\.com|hh\.ru|superjob\.ru|2gis\.ru|yandex\.ru/maps|rusprofile\.ru|fparf\.ru|sbis\.ru|spark-interfax\.ru)\S{0,80}", re.IGNORECASE)
_INN_RE = re.compile(r"\b(?:ИНН|ОГРН|ОГРНИП|КПП)[\s:№#]*\d{10,15}\b", re.IGNORECASE)


def html_to_text(html: str) -> str:
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = _TAG_RE.sub(" ", body)
    return _WS_RE.sub(" ", body).strip()


def goal_conditioned_extract(text: str, anchor: dict, *, budget: int = SCRAPE_BUDGET_CHARS) -> str:
    """Pull anchor mentions + contact / social patterns ±400 chars.

    Falls back to text head if no match. Returns ≤budget chars.
    """
    if not text:
        return ""
    spans: list[tuple[int, int]] = []
    name = (anchor.get("name") or "").strip()

    def add_match(start: int, end: int, pad: int = 400) -> None:
        s = max(0, start - pad)
        e = min(len(text), end + pad)
        spans.append((s, e))

    # anchor name (case-insensitive)
    if name:
        for m in re.finditer(re.escape(name), text, flags=re.IGNORECASE):
            add_match(m.start(), m.end(), pad=400)
    # anchor.oid
    oid = str(anchor.get("oid") or "")
    if oid:
        for m in re.finditer(re.escape(oid), text):
            add_match(m.start(), m.end(), pad=200)
    # contact patterns
    for rx, pad in [(_PHONE_RE, 200), (_EMAIL_RE, 200), (_SOCIAL_RE, 100), (_INN_RE, 200)]:
        for m in rx.finditer(text):
            add_match(m.start(), m.end(), pad=pad)

    if not spans:
        return text[:budget]

    # merge overlapping
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 50:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    out_parts: list[str] = []
    total = 0
    for s, e in merged:
        chunk = text[s:e].strip()
        if not chunk:
            continue
        out_parts.append(chunk)
        total += len(chunk)
        if total >= budget:
            break
    out = " || ".join(out_parts)
    return out[:budget]

# --- tool: web_serp + web_scrape -------------------------------------------

async def tool_web_serp(http: httpx.AsyncClient, query: str, k: int = 6) -> dict:
    try:
        r = await http.get(SEARXNG_URL,
                           params={"q": query, "format": "json", "language": "ru"},
                           headers=SEARXNG_HEADERS, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        seen: set[str] = set()
        results = []
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
            if len(results) >= max(1, min(k, 10)):
                break
        return {"query": query, "count": len(results), "results": results}
    except Exception as e:
        return {"query": query, "error": str(e)[:200], "results": []}


async def tool_web_scrape(http: httpx.AsyncClient, url: str, anchor: dict) -> dict:
    try:
        r = await http.get(url, timeout=SCRAPE_TIMEOUT_S, follow_redirects=True,
                           headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        if r.status_code >= 400:
            return {"url": url, "error": f"http {r.status_code}", "text": "", "length": 0, "ok": False}
        full = html_to_text(r.text)
        extract = goal_conditioned_extract(full, anchor)
        return {
            "url": url, "text": extract, "length": len(full),
            "extract_chars": len(extract), "ok": True,
        }
    except Exception as e:
        return {"url": url, "error": str(e)[:200], "text": "", "length": 0, "ok": False}

# --- auxiliary LLM call: refraser ------------------------------------------

REFRASER_SYSTEM = """You are a research SUPERVISOR. The agent has done some web searches. Your job: propose 2-3 NEW search angles the agent hasn't tried yet, to widen coverage of an org research task.

Rules:
- Each angle is a short Russian query (≤5 words), suitable for SearXNG.
- Do NOT repeat or rephrase queries from the agent's history.
- Aim at coverage gaps: e.g. if no social was found — propose social platforms; if no vacancies — propose vacancy boards; if no reviews — propose review aggregators.
- Output strict JSON: {"new_angles": ["...", "...", "..."], "reason": "<≤25 words>"}
- No prose outside the JSON."""


async def refraser_call(
    llm: AsyncOpenAI, model: str,
    anchor: dict, queries_history: list[str], visited_urls: set[str], schema_snapshot: dict,
    *, usage_counter: dict,
) -> dict:
    """Auxiliary LLM call producing 2-3 new search angles."""
    snap_str = json.dumps({
        "filled": [k for k, v in schema_snapshot.items() if v and (not isinstance(v, (list, dict)) or len(v) > 0)],
        "empty": [k for k, v in schema_snapshot.items() if not v or (isinstance(v, (list, dict)) and len(v) == 0)],
    }, ensure_ascii=False)
    user = (
        f"ANCHOR: {anchor.get('name')} ({anchor.get('address')}), категории: {anchor.get('categories')}\n"
        f"QUERIES SO FAR ({len(queries_history)}):\n  - " + "\n  - ".join(queries_history[-12:]) + "\n"
        f"VISITED URL DOMAINS: {sorted({urlparse(u).netloc for u in visited_urls})[:20]}\n"
        f"SCHEMA STATE (top-level): {snap_str}\n"
        f"Propose 2-3 NEW angles. Return JSON only."
    )
    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": REFRASER_SYSTEM},
                {"role": "user", "content": user},
            ],
            timeout=LLM_TIMEOUT_S,
        )
    except Exception as e:
        return {"new_angles": [], "reason": f"refraser error: {type(e).__name__}"}

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    content = (resp.choices[0].message.content or "").strip()
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return {"new_angles": [], "reason": "no json"}
    try:
        parsed = json.loads(m.group(0))
        angles = [str(a)[:80] for a in (parsed.get("new_angles") or []) if a][:3]
        return {"new_angles": angles, "reason": str(parsed.get("reason", ""))[:160]}
    except Exception:
        return {"new_angles": [], "reason": "parse fail"}

# --- auxiliary LLM call: critic (submit gate) ------------------------------

CRITIC_SYSTEM = """You are a research QUALITY CRITIC. The agent has assembled an ORG_CARD and wants to submit. Evaluate the card.

Output strict JSON: {"score": <0-10 float>, "missing": ["<field>", ...], "wrong": ["<short desc>", ...], "feedback": "<≤200 char actionable advice>", "verdict": "pass"|"reject"}

Scoring rubric (be CALIBRATED, not harsh):
- 10: every reasonable field populated with grounded data; strong source diversity
- 9: most fields populated; 1-2 minor gaps; sources solid
- 8: core fields present (what_they_do, ≥1 site, ≥1 phone or email, sources); 2-3 obvious gaps
- 7: usable card; some core fields empty or thin
- 5-6: skeleton only; many core fields empty
- 0-4: hallucination, entity confusion, or near-empty

Set verdict="pass" if score ≥ 8.5 OR if the only gaps are clearly absent in the real world (e.g. small org has no tech_stack — that's fine).
Set verdict="reject" if score < 8.5 AND the missing fields are realistically findable on the web.

ANCHOR validation:
- If card phones don't include any anchor.yandex_phones → verdict="reject" (entity confusion risk)
- If card.sources contains non-URL entries → verdict="reject"

No prose outside the JSON."""


async def critic_call(
    llm: AsyncOpenAI, model: str,
    anchor: dict, card: dict, visited_urls: set[str], queries_history: list[str],
    *, usage_counter: dict,
) -> dict:
    """Auxiliary LLM call evaluating the proposed card. Returns score + verdict."""
    try:
        card_str = json.dumps(card, ensure_ascii=False, indent=2)[:6000]
    except Exception:
        card_str = str(card)[:6000]
    user = (
        f"ANCHOR:\n  name: {anchor.get('name')}\n  address: {anchor.get('address')}\n"
        f"  yandex_phones: {anchor.get('yandex_phones')}\n  categories: {anchor.get('categories')}\n\n"
        f"AGENT'S PROPOSED CARD:\n{card_str}\n\n"
        f"AGENT'S RESEARCH STATS:\n  queries_made: {len(queries_history)}\n"
        f"  urls_visited: {len(visited_urls)}\n\n"
        f"Evaluate. Return JSON only."
    )
    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM},
                {"role": "user", "content": user},
            ],
            timeout=LLM_TIMEOUT_S,
        )
    except Exception as e:
        # Fail open — let submit through to avoid blocking on critic outage
        return {"score": 10.0, "missing": [], "wrong": [],
                "feedback": f"critic unreachable: {type(e).__name__}",
                "verdict": "pass"}

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    content = (resp.choices[0].message.content or "").strip()
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return {"score": 7.0, "missing": [], "wrong": [], "feedback": "critic returned non-JSON; passing",
                "verdict": "pass"}
    try:
        p = json.loads(m.group(0))
        return {
            "score": float(p.get("score", 7.0)),
            "missing": [str(x)[:80] for x in (p.get("missing") or [])][:8],
            "wrong": [str(x)[:120] for x in (p.get("wrong") or [])][:5],
            "feedback": str(p.get("feedback", ""))[:300],
            "verdict": p.get("verdict", "pass"),
        }
    except Exception:
        return {"score": 7.0, "missing": [], "wrong": [],
                "feedback": "critic parse fail; passing", "verdict": "pass"}


# --- hard compaction --------------------------------------------------------

COMPACT_SYSTEM = """You produce a concise research digest so an agent can continue with a smaller context.

Output strict JSON:
- schema_state_so_far: partial ORG_CARD (only confirmed fields)
- queries_history: list of queries already tried
- urls_visited: list of {url, verdict} ("useful"|"empty"|"dead")
- key_facts: up to 15 useful claims with source URL
- open_gaps: list of ORG_CARD top-level fields still missing
- hypotheses: ≤5 short strings about identity / strategy

No prose outside the JSON."""


async def compact_context(
    llm: AsyncOpenAI, model: str,
    messages: list[dict], state: "AgentState",
    *, usage_counter: dict,
) -> list[dict]:
    blob_parts: list[str] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        content = m.get("content") or ""
        if role == "tool":
            blob_parts.append(f"[tool_result {m.get('name', '?')}]\n{str(content)[:2500]}")
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                tc_sum = "; ".join(
                    f"{tc['function']['name']}({tc['function']['arguments'][:200]})" for tc in tcs
                )
                blob_parts.append(f"[asst tool_calls] {tc_sum}")
            if content:
                blob_parts.append(f"[asst] {str(content)[:1200]}")
        elif role == "user":
            blob_parts.append(f"[user]\n{str(content)[:2500]}")
    blob = "\n\n".join(blob_parts)[:55000]

    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COMPACT_SYSTEM},
                {"role": "user", "content": f"Summarize this research so far:\n\n{blob}"},
            ],
            timeout=LLM_TIMEOUT_S,
        )
    except Exception:
        return messages

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    digest = (resp.choices[0].message.content or "").strip()
    state.compaction_count += 1
    new_msgs = [messages[0], messages[1]]
    new_msgs.append({
        "role": "assistant",
        "content": f"[AUTO-COMPACTION #{state.compaction_count} — research digest, {len(digest)} chars]\n\n{digest}",
    })
    new_msgs.append({"role": "user", "content":
        f"Context was auto-compacted. You have {MAX_COMPACTIONS - state.compaction_count} compactions left. "
        f"Focus on open_gaps from the digest. Submit soon."})
    return new_msgs

# --- soft compaction --------------------------------------------------------

def _strip_meta(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        out.append({k: v for k, v in m.items() if not (isinstance(k, str) and k.startswith("_"))})
    return out


def soft_elide(messages: list[dict], current_turn: int) -> int:
    cutoff = current_turn - SOFT_ELIDE_AFTER_TURNS
    elided = 0
    for m in messages:
        if m.get("role") != "tool":
            continue
        if m.get("_turn", 0) > cutoff or m.get("_elided") or m.get("name") != "web_scrape":
            continue
        content = m.get("content") or ""
        if len(content) <= 400:
            continue
        try:
            d = json.loads(content)
            url_hint = d.get("url", "")[:120] if isinstance(d, dict) else ""
        except Exception:
            url_hint = ""
        m["content"] = json.dumps({
            "_elided": True, "url": url_hint,
            "note": f"scrape result elided (older than {SOFT_ELIDE_AFTER_TURNS} turns; use the facts you already extracted).",
        }, ensure_ascii=False)
        m["_elided"] = True
        elided += 1
    return elided

# --- card sanitization ------------------------------------------------------

def sanitize_card(card: dict, visited_urls: set[str]) -> dict:
    """Drop sources with non-URL `url` entries; warn-only on other oddities."""
    if not isinstance(card, dict):
        return card
    srcs = card.get("sources") or []
    clean = []
    dropped = []
    for s in srcs:
        if not isinstance(s, dict):
            dropped.append(repr(s)[:80])
            continue
        url = (s.get("url") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            dropped.append(url[:80])
            continue
        host = urlparse(url).netloc
        if "." not in host:
            dropped.append(url[:80])
            continue
        clean.append(s)
    if dropped:
        card["_sanitize_dropped_sources"] = dropped
    card["sources"] = clean
    return card

# --- state ------------------------------------------------------------------

@dataclass
class AgentState:
    anchor: dict
    schema_state_seed: dict
    serp_call_count: int = 0
    queries_history: list[str] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    domain_fail_count: dict[str, int] = field(default_factory=dict)
    compaction_count: int = 0
    schema_snapshot: dict = field(default_factory=dict)  # last submitted/refraser snapshot
    submit_attempts: int = 0
    critic_history: list[dict] = field(default_factory=list)


def update_schema_snapshot_from_card_attempts(state: AgentState, card: dict | None) -> None:
    if isinstance(card, dict):
        state.schema_snapshot = card

# --- main loop --------------------------------------------------------------

async def run_agent(model_key: str, oid: str) -> dict:
    cfg = MODELS[model_key]
    llm = AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"],
                      timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0), max_retries=2)
    http = httpx.AsyncClient()

    target = load_target(oid)
    anchor = build_anchor(target["org"])
    user_msg = build_user_message(target)

    state = AgentState(
        anchor=anchor,
        schema_state_seed={
            "yandex_maps": {
                "rating": target["org"].get("rating"),
                "reviews_count": target["org"].get("reviewsCount"),
                "reviews_sample": [(r.get("text") or "").strip()[:300]
                                   for r in (target["reviews"] or [])
                                   if (r.get("text") or "").strip()][:6],
            },
            "contacts": {
                "phones": [{"number": p["number"], "context": "yandex.maps card"}
                           for p in (target["org"].get("phones") or []) if p.get("number")],
                "websites": [target["org"]["site"]] if target["org"].get("site") else [],
            },
        },
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    trace: list[dict] = []
    submitted_card: dict | None = None

    started = time.time()
    main_usage = {"prompt": 0, "completion": 0, "last_prompt": 0}
    aux_usage = {"prompt": 0, "completion": 0}
    tool_call_count = {"web_serp": 0, "web_scrape": 0, "submit_org_card": 0}
    refraser_runs = 0

    for turn in range(1, MAX_TURNS + 1):
        elided = soft_elide(messages, turn)
        if elided:
            trace.append({"turn": turn, "role": "soft_compact", "elided": elided})

        t0 = time.time()
        try:
            resp = await llm.chat.completions.create(
                model=cfg["model"], messages=_strip_meta(messages),
                tools=TOOLS, tool_choice="auto",
            )
        except Exception as e:
            trace.append({"turn": turn, "role": "error", "content": f"main LLM call failed: {e!r}"[:500]})
            break
        elapsed = time.time() - t0

        u = getattr(resp, "usage", None)
        if u:
            pt = getattr(u, "prompt_tokens", 0) or 0
            ct = getattr(u, "completion_tokens", 0) or 0
            main_usage["prompt"] += pt
            main_usage["completion"] += ct
            main_usage["last_prompt"] = pt
        msg = resp.choices[0].message
        tcs = getattr(msg, "tool_calls", None) or []

        asst_rec: dict = {"role": "assistant", "content": msg.content or ""}
        if tcs:
            asst_rec["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ]
        messages.append(asst_rec)
        trace.append({
            "turn": turn, "role": "assistant",
            "content": (msg.content or "")[:600],
            "tool_calls": [{"name": tc.function.name, "args": tc.function.arguments[:400]} for tc in tcs],
            "elapsed_s": round(elapsed, 2),
            "main_prompt_tokens": main_usage["last_prompt"],
        })

        # Hard-compaction trigger (before executing tools, but we have to keep our pending tool_calls valid)
        if (main_usage["last_prompt"] >= TOKEN_BUDGET
                and state.compaction_count < MAX_COMPACTIONS):
            trace.append({"turn": turn, "role": "compact_trigger",
                          "last_prompt_tokens": main_usage["last_prompt"],
                          "compaction_n": state.compaction_count + 1})
            # Drop the just-appended assistant message (it had tool_calls that we won't execute)
            messages.pop()
            messages = await compact_context(llm, cfg["model"], messages, state, usage_counter=aux_usage)
            continue

        if not tcs:
            trace.append({"turn": turn, "role": "note", "content": "Model did not call any tool — stopping."})
            break

        for tc in tcs:
            name = tc.function.name
            tool_call_count[name] = tool_call_count.get(name, 0) + 1
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            tt = time.time()
            if name == "web_serp":
                q = args.get("query", "")
                k = int(args.get("k") or 6)
                state.queries_history.append(q)
                state.serp_call_count += 1
                result = await tool_web_serp(http, q, k=k)

                # Domain-block hint
                blocked = sorted([d for d, c in state.domain_fail_count.items() if c >= DOMAIN_FAIL_THRESHOLD])
                if blocked:
                    result["_blocked_domains"] = blocked

                # Refraser every Nth serp
                if state.serp_call_count % REFRASER_EVERY_N_SERPS == 0:
                    refraser_runs += 1
                    ref = await refraser_call(
                        llm, cfg["model"], anchor,
                        state.queries_history, state.visited_urls, state.schema_snapshot or state.schema_state_seed,
                        usage_counter=aux_usage,
                    )
                    if ref.get("new_angles"):
                        result["_supervisor_hint"] = {
                            "new_angles": ref["new_angles"],
                            "reason": ref.get("reason", ""),
                        }
                        trace.append({"turn": turn, "role": "refraser",
                                      "angles": ref["new_angles"],
                                      "reason": ref.get("reason", "")})

            elif name == "web_scrape":
                url = args.get("url", "")
                state.visited_urls.add(url)
                result = await tool_web_scrape(http, url, anchor)
                # Track domain failures — but never block whitelisted domains
                if not result.get("ok"):
                    dom = urlparse(url).netloc
                    if dom and dom not in DOMAINS_NEVER_BLOCK:
                        state.domain_fail_count[dom] = state.domain_fail_count.get(dom, 0) + 1

            elif name == "submit_org_card":
                raw = args.get("card") or args
                update_schema_snapshot_from_card_attempts(state, raw)
                proposed = sanitize_card(raw if isinstance(raw, dict) else {}, state.visited_urls)
                # Critic gate
                state.submit_attempts += 1
                critic_verdict = await critic_call(
                    llm, cfg["model"], anchor, proposed,
                    state.visited_urls, state.queries_history,
                    usage_counter=aux_usage,
                )
                trace.append({"turn": turn, "role": "critic",
                              "score": critic_verdict["score"],
                              "verdict": critic_verdict["verdict"],
                              "missing": critic_verdict["missing"],
                              "wrong": critic_verdict["wrong"],
                              "feedback": critic_verdict["feedback"]})

                # Decide
                force_accept = state.submit_attempts >= MAX_SUBMIT_REJECTS + 1
                if (critic_verdict["score"] >= CRITIC_PASS_SCORE
                        or critic_verdict["verdict"] == "pass"
                        or force_accept):
                    submitted_card = proposed
                    result = {
                        "submitted": True,
                        "critic_score": critic_verdict["score"],
                        "critic_verdict": "passed (force-accept)" if force_accept and critic_verdict["score"] < CRITIC_PASS_SCORE else "passed",
                    }
                else:
                    # Reject: pull a refraser for new angles to fix the gaps
                    ref = await refraser_call(
                        llm, cfg["model"], anchor,
                        state.queries_history, state.visited_urls, proposed or {},
                        usage_counter=aux_usage,
                    )
                    refraser_runs += 1
                    if ref.get("new_angles"):
                        trace.append({"turn": turn, "role": "refraser",
                                      "angles": ref["new_angles"],
                                      "reason": ref.get("reason", ""),
                                      "trigger": "submit_reject"})
                    result = {
                        "submitted": False,
                        "rejected_by_critic": True,
                        "critic_score": critic_verdict["score"],
                        "critic_feedback": critic_verdict["feedback"],
                        "missing_fields": critic_verdict["missing"],
                        "wrong_things": critic_verdict["wrong"],
                        "suggested_new_angles": ref.get("new_angles", []),
                        "attempts_remaining_before_force": max(0, MAX_SUBMIT_REJECTS - state.submit_attempts + 1),
                        "instruction": (
                            f"Critic scored your card {critic_verdict['score']:.1f}/10 (need ≥{CRITIC_PASS_SCORE}). "
                            f"Address the missing/wrong items. If you've truly exhausted the web, submit again — "
                            f"after {MAX_SUBMIT_REJECTS} rejections the system will force-accept."
                        ),
                    }
            else:
                result = {"error": f"unknown tool {name}"}

            t_elapsed = time.time() - tt
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": name,
                "content": json.dumps(result, ensure_ascii=False)[:8000],
                "_turn": turn,
            })
            trace.append({
                "turn": turn, "role": "tool", "tool_name": name,
                "args": json.dumps(args, ensure_ascii=False)[:400],
                "result_preview": json.dumps(result, ensure_ascii=False)[:500],
                "elapsed_s": round(t_elapsed, 2),
            })

        if submitted_card is not None:
            break

        # Post-tool hard-compaction guard
        if (main_usage["last_prompt"] >= int(TOKEN_BUDGET * 0.85)
                and state.compaction_count < MAX_COMPACTIONS):
            trace.append({"turn": turn, "role": "compact_trigger_post",
                          "last_prompt_tokens": main_usage["last_prompt"]})
            messages = await compact_context(llm, cfg["model"], messages, state, usage_counter=aux_usage)

    if submitted_card is None:
        submitted_card = {"_force_submit": True, "card_from_state_seed": state.schema_state_seed}
        trace.append({"turn": "post", "role": "note", "content": "Forced submit on exit (no submit_org_card called)."})

    await http.aclose()
    total_elapsed = time.time() - started

    critic_events = [t for t in trace if t.get("role") == "critic"]
    return {
        "model": model_key,
        "model_id": cfg["model"],
        "oid": oid,
        "anchor": anchor,
        "elapsed_s": round(total_elapsed, 1),
        "turns": len([t for t in trace if t.get("role") == "assistant"]),
        "tool_call_counts": tool_call_count,
        "refraser_runs": refraser_runs,
        "submit_attempts": state.submit_attempts,
        "critic_events": critic_events,
        "compactions": state.compaction_count,
        "blocked_domains_at_end": sorted([d for d, c in state.domain_fail_count.items() if c >= DOMAIN_FAIL_THRESHOLD]),
        "tokens": {
            "main": main_usage,
            "aux": aux_usage,
            "grand_total": (main_usage["prompt"] + main_usage["completion"]
                            + aux_usage["prompt"] + aux_usage["completion"]),
        },
        "submitted_card": submitted_card,
        "queries_history": state.queries_history,
        "visited_urls": sorted(state.visited_urls),
        "trace": trace,
    }


# --- runner -----------------------------------------------------------------

async def main() -> int:
    model_key = os.environ.get("MODEL", "local")
    oid = os.environ.get("OID", "226497224828")
    if model_key not in MODELS:
        print(f"Unknown MODEL={model_key}. Options: {list(MODELS)}")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"v2_1__{oid}__{model_key}.json"

    print(f"[*] simple_agent_v2.1 on model={model_key} ({MODELS[model_key]['model']})")
    print(f"[*] OID={oid}, output → {out_path.name}")
    print(f"[*] Budget: {TOKEN_BUDGET} prompt_tokens, max_compactions={MAX_COMPACTIONS}, "
          f"soft_elide_after={SOFT_ELIDE_AFTER_TURNS}, refraser_every={REFRASER_EVERY_N_SERPS}, "
          f"critic_pass={CRITIC_PASS_SCORE}/10, max_rejects={MAX_SUBMIT_REJECTS}")

    result = await run_agent(model_key, oid)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[+] Done in {result['elapsed_s']}s, turns={result['turns']}, "
          f"calls={result['tool_call_counts']}, refraser_runs={result['refraser_runs']}, "
          f"submit_attempts={result['submit_attempts']}, compactions={result['compactions']}")
    if result.get("critic_events"):
        scores = [c["score"] for c in result["critic_events"]]
        verdicts = [c["verdict"] for c in result["critic_events"]]
        print(f"[+] Critic scores: {scores} verdicts: {verdicts}")
    print(f"[+] Tokens: main={result['tokens']['main']}, aux={result['tokens']['aux']}")
    print(f"[+] Grand total: {result['tokens']['grand_total']}")
    if result.get("blocked_domains_at_end"):
        print(f"[+] Blocked domains: {result['blocked_domains_at_end']}")
    print(f"[+] Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
