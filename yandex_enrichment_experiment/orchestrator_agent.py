"""Orchestrator + sub-agents version of the research agent.

Design rationale (see chat with user):
- The flat 2-tool simple_agent works well but eats huge context (87k-378k tokens).
- Pages with high relevance score → orchestrator reads itself (full text into chat).
- Pages with medium score → delegated to a same-model sub-agent which returns only
  compact JSON findings, keeping the orchestrator chat lean.
- Hard token budget for the orchestrator (90k prompt_tokens via API usage), with up
  to 2 automatic context compactions before forcing a submit.
- Yandex.Maps card + reviews are pre-loaded from `data/organizations.json` and
  `data/reviews/{oid}.json` and injected into the initial user message — the
  orchestrator does NOT spend turns re-fetching what we already have.

Tools exposed to the orchestrator:
    web_serp(query, k)          — SearXNG search; results are auto-scored by an
                                  auxiliary LLM call before being returned.
    read_page(url)              — orchestrator self-reads (use when score >= 8.5).
    delegate_read(url, gap)     — sub-agent reads + extracts (use when 6.5 <= score < 8.5).
    delegate_verify(claim, urls)— sub-agent with NO tools, verifies a claim against
                                  already-fetched pages. Max 5 calls per research.
    submit_org_card(card)       — terminal.

Usage:
    MODEL=local|openrouter-qwen|openrouter-deepseek \
    OID=226497224828 \
    uv run python orchestrator_agent.py
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

# --- thresholds / budgets --------------------------------------------------

TOKEN_BUDGET = 90_000             # hard cap on orchestrator prompt_tokens (latest call)
MAX_COMPACTIONS = 2               # how many times we can hard-compact
SOFT_ELIDE_AFTER_TURNS = 6        # old read_page/delegate_read tool_results elided after N turns
MAX_VERIFY_CALLS = 5              # sub-agent verify hard cap
MAX_ORCH_TURNS = 30
ORCH_TIMEOUT_S = 240.0
SUB_TIMEOUT_S = 120.0
SCORE_HIGH = 8.5
SCORE_MED = 6.5

# --- ORG_CARD_SCHEMA (identical to simple_agent) ---------------------------

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

# --- target loading --------------------------------------------------------

def load_target(oid: str) -> dict:
    """Pull yandex card + reviews for the given oid from on-disk JSON."""
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
    """Compact identity record passed to every sub-agent."""
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


def build_initial_user_message(target: dict) -> str:
    org = target["org"]
    reviews = target["reviews"]
    anchor = build_anchor(org)
    cats = ", ".join(anchor["categories"]) or "—"
    phones = ", ".join(anchor["yandex_phones"]) or "—"

    rev_snippets: list[str] = []
    for r in reviews[:8]:
        txt = (r.get("text") or "").strip().replace("\n", " ")
        if not txt:
            continue
        rev_snippets.append(f"- ({r.get('rating', '?')}/5) {txt[:280]}")
    rev_block = "\n".join(rev_snippets) if rev_snippets else "(нет отзывов с текстом)"

    return f"""Цель: собрать карточку организации (ORG_CARD_SCHEMA).

ANCHOR (целевая организация, ground truth — не путать с другими):
- name: {anchor['name']}
- oid (yandex): {anchor['oid']}
- адрес: {anchor['address']}
- город: {anchor['city']}
- категории: {cats}
- телефоны (из yandex card): {phones}
- yandex.maps URL: {anchor['yandex_url']}
- сайт (если известен из yandex card): {anchor['yandex_site'] or 'не указан в карточке'}

Рейтинг yandex.maps: {org.get('rating', '—')} ({org.get('reviewsCount', 0)} отзывов).

Отзывы (top {len(rev_snippets)}) — используй для problems_signals и yandex_maps.reviews_sample:
{rev_block}

ЗАДАЧА: дополнить карточку из веба:
- what_they_do — точное описание услуг/продуктов
- scale_indicators — масштаб (локации, сотрудники, оборот)
- tech_stack — упоминаемые технологии
- vacancies — открытые вакансии (hh.ru / superjob / career page)
- social — VK, Telegram, Instagram, YouTube, LinkedIn, Habr (по anchor.oid/name)
- contacts.emails, contacts.websites — email с контекстом, все сайты
- problems_signals — pain points из отзывов + жалобы из веба

ВАЖНО:
- Anchor.address и anchor.phones — единственный источник истины об идентичности.
  При любом совпадении имени, но другом городе/адресе/телефоне — это ДРУГАЯ организация, игнорируй.
- yandex_maps секцию заполни сразу из данных выше (rating, reviews_count, reviews_sample, hours если есть).
- НЕ выдумывай. Пустое поле → пустой массив / строка / null.
- Контекстное окно ограничено: для не-критичных URL используй delegate_read.
"""

# --- tool schemas ----------------------------------------------------------

ORCH_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "web_serp",
            "description": (
                "Search via SearXNG. Returns each result with a relevance score 0-10 "
                "(scored by an auxiliary LLM, do NOT score yourself). "
                "Use short queries (≤5 Russian/English words)."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
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
            "name": "read_page",
            "description": (
                "Fetch a URL yourself — full text (up to 8 KB) returned into your chat. "
                "USE ONLY when score >= 8.5 (high-confidence primary source). "
                "Each call costs ~2-4k tokens of your context window."
            ),
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
            "name": "delegate_read",
            "description": (
                "Delegate reading a URL to a sub-agent. Sub-agent gets a compact brief "
                "(anchor + open gaps + top facts) plus the raw page, and returns only "
                "structured findings (~300 tokens). "
                "USE for score in [6.5, 8.5) — saves your context window."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "gap"],
                "properties": {
                    "url": {"type": "string"},
                    "gap": {
                        "type": "string",
                        "description": "What you hope this page provides (e.g. 'vk profile', 'phone email', 'vacancies').",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_verify",
            "description": (
                "Send a single claim + list of already-fetched URLs to a no-tools sub-agent. "
                "Sub-agent inspects cached page contents and returns "
                "{verdict: confirm|deny|unsure, evidence, cited_url}. "
                f"Max {MAX_VERIFY_CALLS} verify calls per research."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim", "urls"],
                "properties": {
                    "claim": {"type": "string", "description": "The specific assertion to verify."},
                    "urls": {
                        "type": "array",
                        "minItems": 1, "maxItems": 4,
                        "items": {"type": "string"},
                        "description": "URLs that must be in the page cache (you read or delegated them).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_org_card",
            "description": "Terminal: submit the final ORG_CARD. Call ONCE when ready. Empty fields are fine — never hallucinate.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["card"],
                "properties": {"card": ORG_CARD_SCHEMA},
            },
        },
    },
]

ORCH_SYSTEM_PROMPT = """You are an ORCHESTRATOR agent researching a single organization.

Tools available:
- web_serp(query, k): SearXNG search. Each result comes back WITH a relevance score (0-10) and a reason. The score is computed for you by a separate LLM — trust it.
- read_page(url): self-read, full text into your context. Use ONLY when score >= 8.5.
- delegate_read(url, gap): sub-agent reads, returns compact findings (~300 tok). Use when 6.5 <= score < 8.5. Saves your context budget.
- delegate_verify(claim, urls): no-tools sub-agent verifies a claim against already-fetched URLs. Use sparingly to confirm risky claims. Max 5 calls.
- submit_org_card(card): terminal — submit final card.

Workflow:
1. Start with the ANCHOR + reviews already in the user message — those are pre-extracted facts.
2. Plan 2-4 short SERP queries to fill what's missing (websites, social, vacancies, emails).
3. For each SERP result, decide based on its score whether to read yourself or delegate.
4. Periodically verify critical claims (e.g. that a found email/phone really belongs to anchor).
5. Submit when major fields are filled or evidence is exhausted.

Rules:
- ANCHOR is ground truth for identity. Any URL whose content contradicts anchor city/address/phone is for a DIFFERENT entity — discard it.
- Do NOT hallucinate. Missing data → empty array / null / "".
- Stay efficient: prefer delegate_read for borderline-score URLs. Your context window is limited.
- Russian content in Russian, English in English. Match anchor language for queries (here: Russian).
- yandex_maps section is already provided in the user message — copy rating/reviews_count/hours/sample directly, don't re-fetch.

When confident — submit_org_card. Do NOT write the JSON in chat; CALL the tool.
"""

# --- auxiliary LLM call: relevance scoring ---------------------------------

SCORE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "submit_scores",
        "description": "Submit relevance scores for the listed search results.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scores"],
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["index", "score", "reason"],
                        "properties": {
                            "index": {"type": "integer", "description": "0-based index into the input results list."},
                            "score": {"type": "number", "description": "Relevance score 0-10."},
                            "reason": {"type": "string", "description": "≤15 words on why."},
                        },
                    },
                },
            },
        },
    },
}

SCORE_SYSTEM_PROMPT = """You rate web search results for relevance to a research task.

Scoring rubric (0-10):
- 9-10: official primary source for the target org (official .ru/.рф site matching anchor.name; yandex.maps/2gis page with matching oid; hh.ru employer page; rusprofile by exact ИНН/name).
- 7-8: likely useful but needs filtering (VK profile match, news with anchor name, business directories).
- 4-6: tangentially related, listings, generic services pages with no obvious anchor match.
- 0-3: irrelevant, foreign-language, spam, listings unrelated to anchor, PDFs, github code.

Penalties:
- If snippet/title mentions a different city or address than anchor — score ≤4 (different entity risk).
- If URL is .pdf or github.com — score 0.
- If URL is in already-visited list — score 0 (no point re-fetching).

Call submit_scores with one entry per input result."""

async def score_urls_via_llm(
    llm: AsyncOpenAI,
    model: str,
    anchor: dict,
    goal_summary: str,
    results: list[dict],
    visited: set[str],
    *,
    usage_counter: dict,
) -> list[dict]:
    """Auxiliary LLM call that adds .score and .reason to each result."""
    if not results:
        return []
    lines = [f"Anchor: {anchor.get('name')} | {anchor.get('address')} | категории: {', '.join(anchor.get('categories', []))}",
             f"Goal: {goal_summary}",
             f"Already visited URLs (score 0): {sorted(visited)[:20]}",
             "Results to score:"]
    for i, r in enumerate(results):
        lines.append(f"{i}: {r.get('url')} | {r.get('title', '')[:140]} | {r.get('snippet', '')[:200]}")
    user = "\n".join(lines)

    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SCORE_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            tools=[SCORE_TOOL],
            tool_choice="auto",
        )
    except Exception as e:
        # Fallback: equal medium scores
        for r in results:
            r["score"] = 6.0
            r["reason"] = f"score-fallback ({type(e).__name__})"
        return results

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    msg = resp.choices[0].message
    tcs = getattr(msg, "tool_calls", None) or []
    score_map: dict[int, dict] = {}
    if tcs:
        try:
            args = json.loads(tcs[0].function.arguments or "{}")
            for s in args.get("scores") or []:
                idx = s.get("index")
                if isinstance(idx, int):
                    score_map[idx] = {"score": float(s.get("score", 5.0)), "reason": str(s.get("reason", ""))[:200]}
        except Exception:
            pass

    for i, r in enumerate(results):
        sm = score_map.get(i, {"score": 5.0, "reason": "default (no score returned)"})
        # Hard rules in addition to LLM score
        url = r.get("url", "")
        if url in visited:
            sm = {"score": 0.0, "reason": "already visited"}
        elif url.lower().endswith(".pdf") or "github.com" in url:
            sm = {"score": 0.0, "reason": "pdf/github (no useful content)"}
        r["score"] = round(sm["score"], 2)
        r["reason"] = sm["reason"]
    return results

# --- tool implementations: web_serp, fetch_url -----------------------------

async def web_serp_call(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict]:
    try:
        r = await http.get(SEARXNG_URL,
                           params={"q": query, "format": "json", "language": "ru"},
                           headers=SEARXNG_HEADERS, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        seen: set[str] = set()
        out: list[dict] = []
        for item in (data.get("results") or []):
            link = item.get("url") or ""
            if not link.startswith("http") or link in seen:
                continue
            seen.add(link)
            out.append({
                "url": link,
                "title": (item.get("title") or "").strip(),
                "snippet": (item.get("content") or "").strip()[:300],
            })
            if len(out) >= max(1, min(k, 10)):
                break
        return out
    except Exception as e:
        return [{"error": str(e)[:200], "url": "", "title": "", "snippet": ""}]


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

async def fetch_url(http: httpx.AsyncClient, url: str, *, max_chars: int = 8000) -> dict:
    try:
        r = await http.get(url, timeout=15.0, follow_redirects=True,
                           headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        if r.status_code >= 400:
            return {"url": url, "error": f"http {r.status_code}", "text": "", "length": 0}
        body = r.text
        body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = _HTML_TAG_RE.sub(" ", body)
        body = _WS_RE.sub(" ", body).strip()
        return {"url": url, "text": body[:max_chars], "length": len(body)}
    except Exception as e:
        return {"url": url, "error": str(e)[:200], "text": "", "length": 0}

# --- sub-agent: delegated read ---------------------------------------------

SUBAGENT_READ_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "submit_findings",
        "description": "Submit your structured findings from the page.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["fills", "new_facts", "dead_end"],
            "properties": {
                "fills": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Org-card fields you can fill from this page. All optional.",
                    "properties": {
                        "what_they_do": {"type": "string"},
                        "scale_indicators": {"type": "array", "items": {"type": "string"}},
                        "tech_stack": {"type": "array", "items": {"type": "string"}},
                        "vacancies": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                      "properties": {"title": {"type": "string"}, "url": {"type": "string"},
                                      "platform": {"type": "string"}}}},
                        "social_vk": {"type": "array", "items": {"type": "string"}},
                        "social_telegram": {"type": "array", "items": {"type": "string"}},
                        "social_instagram": {"type": "array", "items": {"type": "string"}},
                        "social_youtube": {"type": "array", "items": {"type": "string"}},
                        "social_linkedin": {"type": "array", "items": {"type": "string"}},
                        "social_habr": {"type": "array", "items": {"type": "string"}},
                        "phones": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "properties": {"number": {"type": "string"}, "context": {"type": "string"}}}},
                        "emails": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "properties": {"address": {"type": "string"}, "context": {"type": "string"}}}},
                        "websites": {"type": "array", "items": {"type": "string"}},
                        "problems_signals": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "new_facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["claim"],
                        "properties": {
                            "claim": {"type": "string", "maxLength": 240},
                            "confidence": {"type": "number"},
                        },
                    },
                    "description": "Up to 8 short claims with confidence. Used by orchestrator as context.",
                },
                "dead_end": {
                    "type": "boolean",
                    "description": "True if the page is not about the anchor or has no useful info.",
                },
            },
        },
    },
}

SUBAGENT_READ_SYSTEM = """You are a sub-agent extracting org-card data from ONE web page.

You receive: anchor identity, current schema state (what we know), open gaps, and the raw page text.
You MUST:
- Verify the page describes the anchor (matching name + city/address/phone). If it does not, set dead_end=true and return empty fills.
- Only fill fields that are confirmed by the page.
- Russian text in Russian, no translation.
- For social links — only paste actual URLs from the page (no guesses).
- For phones — only those clearly associated with anchor (not third-party).
- new_facts: up to 8 short claims (≤240 chars each) that the orchestrator might find useful.

Call submit_findings ONCE."""

def build_subagent_brief(state: "OrchState") -> str:
    anchor = state.anchor
    schema = state.schema_state
    gaps = [k for k, v in schema.items() if not v or (isinstance(v, (list, dict)) and len(v) == 0)]
    top_facts = state.known_facts[-5:]
    lines = [
        f"ANCHOR: name={anchor.get('name')!r} | oid={anchor.get('oid')} | address={anchor.get('address')!r} | phones={anchor.get('yandex_phones')} | categories={anchor.get('categories')}",
        f"OPEN GAPS (priority): {gaps}",
        f"TOP-5 KNOWN FACTS: {top_facts}",
    ]
    return "\n".join(lines)


async def delegate_read_call(
    llm: AsyncOpenAI, model: str, http: httpx.AsyncClient,
    state: "OrchState", url: str, gap: str,
    *, usage_counter: dict,
) -> dict:
    """Sub-agent: fetch URL, extract structured findings."""
    page = await fetch_url(http, url, max_chars=12000)  # sub-agent can see a bit more
    if page.get("error"):
        return {"url": url, "error": page["error"], "fills": {}, "new_facts": [], "dead_end": True}

    brief = build_subagent_brief(state)
    user = (f"{brief}\n\nGAP HINT (what orchestrator hopes for): {gap}\n\n"
            f"URL: {url}\n\n=== PAGE TEXT ===\n{page['text']}\n=== END PAGE ===")
    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SUBAGENT_READ_SYSTEM},
                {"role": "user", "content": user},
            ],
            tools=[SUBAGENT_READ_TOOL],
            tool_choice="auto",
            timeout=SUB_TIMEOUT_S,
        )
    except Exception as e:
        return {"url": url, "error": f"subagent llm error: {e!r}"[:200], "fills": {}, "new_facts": [], "dead_end": False}

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    msg = resp.choices[0].message
    tcs = getattr(msg, "tool_calls", None) or []
    if not tcs:
        # Fallback: try to extract JSON from content
        content = (msg.content or "").strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                args = json.loads(match.group(0))
            except Exception:
                args = {"fills": {}, "new_facts": [], "dead_end": False}
        else:
            args = {"fills": {}, "new_facts": [], "dead_end": False}
    else:
        try:
            args = json.loads(tcs[0].function.arguments or "{}")
        except Exception:
            args = {"fills": {}, "new_facts": [], "dead_end": False}

    return {
        "url": url,
        "fills": args.get("fills") or {},
        "new_facts": (args.get("new_facts") or [])[:8],
        "dead_end": bool(args.get("dead_end", False)),
    }

# --- sub-agent: verify (NO TOOLS) ------------------------------------------

SUBAGENT_VERIFY_SYSTEM = """You verify a single claim against already-fetched web pages.

You have NO TOOLS — only the page contents provided. Read them, decide.

Output ONE LINE of strict JSON:
{"verdict": "confirm"|"deny"|"unsure", "evidence": "<≤200 char quote or paraphrase>", "cited_url": "<one URL>"}

If no page even mentions the topic — verdict="unsure", evidence="not mentioned"."""

async def delegate_verify_call(
    llm: AsyncOpenAI, model: str,
    state: "OrchState", claim: str, urls: list[str],
    *, usage_counter: dict,
) -> dict:
    """Sub-agent with no tools. Inspects cached page contents."""
    blocks = []
    used: list[str] = []
    for u in urls[:4]:
        text = state.page_cache.get(u)
        if not text:
            continue
        used.append(u)
        blocks.append(f"=== {u} ===\n{text[:3500]}")
    if not blocks:
        return {"verdict": "unsure", "evidence": "no cached pages for given urls", "cited_url": ""}

    user = (f"CLAIM TO VERIFY:\n{claim}\n\n"
            f"PAGES:\n" + "\n\n".join(blocks))
    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SUBAGENT_VERIFY_SYSTEM},
                {"role": "user", "content": user},
            ],
            timeout=SUB_TIMEOUT_S,
        )
    except Exception as e:
        return {"verdict": "unsure", "evidence": f"llm error: {e!r}"[:200], "cited_url": used[0] if used else ""}

    u_ = getattr(resp, "usage", None)
    if u_:
        usage_counter["prompt"] += getattr(u_, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u_, "completion_tokens", 0) or 0

    content = (resp.choices[0].message.content or "").strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {"verdict": "unsure", "evidence": content[:200], "cited_url": used[0] if used else ""}
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return {"verdict": "unsure", "evidence": content[:200], "cited_url": used[0] if used else ""}
    return {
        "verdict": parsed.get("verdict", "unsure"),
        "evidence": str(parsed.get("evidence", ""))[:300],
        "cited_url": parsed.get("cited_url", used[0] if used else ""),
    }

# --- hard compaction (orchestrator-side) -----------------------------------

COMPACT_SYSTEM = """You produce a tight research digest so an agent can continue working with a smaller context.

Output strict JSON with these keys:
- schema_state_so_far: partial ORG_CARD (only fields you can confirm from facts)
- queries_history: list of search queries already issued
- urls_visited: list of {url, verdict} ("useful"|"empty"|"dead")
- key_facts: up to 15 most useful claims with source URL
- open_gaps: list of ORG_CARD fields still missing
- hypotheses: ≤5 short strings about identity / strategy
- anchor: copy verbatim from the original user message

No prose outside the JSON."""

async def compact_context(
    llm: AsyncOpenAI, model: str,
    messages: list[dict], state: "OrchState",
    *, usage_counter: dict,
) -> list[dict]:
    """Hard-compact: replace mid-history with a digest assistant message."""
    # Build the summarization input — feed the full history as one big user blob
    blob_parts = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        content = m.get("content") or ""
        if role == "tool":
            name = m.get("name", "?")
            blob_parts.append(f"[tool_result {name}]\n{str(content)[:2500]}")
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                tc_summary = "; ".join(
                    f"{tc['function']['name']}({tc['function']['arguments'][:200]})" for tc in tcs
                )
                blob_parts.append(f"[assistant tool_calls]\n{tc_summary}")
            if content:
                blob_parts.append(f"[assistant]\n{str(content)[:1500]}")
        elif role == "user":
            blob_parts.append(f"[user]\n{str(content)[:3000]}")
    blob = "\n\n".join(blob_parts)

    try:
        resp = await llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COMPACT_SYSTEM},
                {"role": "user", "content": f"Summarize this research so far:\n\n{blob[:60000]}"},
            ],
            timeout=ORCH_TIMEOUT_S,
        )
    except Exception as e:
        return messages  # bail; keep original on failure

    u = getattr(resp, "usage", None)
    if u:
        usage_counter["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        usage_counter["completion"] += getattr(u, "completion_tokens", 0) or 0

    digest = (resp.choices[0].message.content or "").strip()
    state.compaction_count += 1

    # Reconstruct messages: keep system + original user + inject digest as assistant + continuation user.
    new_msgs: list[dict] = [messages[0], messages[1]]
    new_msgs.append({
        "role": "assistant",
        "content": f"[AUTO-COMPACTION #{state.compaction_count} — research digest, {len(digest)} chars]\n\n{digest}",
    })
    remaining_budget_warn = (
        f"Context was auto-compacted. You have {MAX_COMPACTIONS - state.compaction_count} compactions left. "
        f"Focus on open_gaps from the digest and submit_org_card soon."
    )
    new_msgs.append({"role": "user", "content": remaining_budget_warn})
    return new_msgs

# --- soft compaction --------------------------------------------------------

def _strip_meta(messages: list[dict]) -> list[dict]:
    """Strip our internal _-prefixed bookkeeping fields before sending to OpenAI API."""
    out: list[dict] = []
    for m in messages:
        clean = {k: v for k, v in m.items() if not (isinstance(k, str) and k.startswith("_"))}
        out.append(clean)
    return out


def soft_elide(messages: list[dict], current_turn: int) -> int:
    """Replace content of old read_page/delegate_read tool messages with a short marker.

    Returns count of elided messages.
    """
    cutoff_turn = current_turn - SOFT_ELIDE_AFTER_TURNS
    elided = 0
    for m in messages:
        if m.get("role") != "tool":
            continue
        if m.get("_turn", 0) > cutoff_turn:
            continue
        if m.get("_elided"):
            continue
        name = m.get("name")
        if name not in ("read_page", "delegate_read"):
            continue
        content = m.get("content") or ""
        if len(content) <= 500:
            continue
        url_hint = ""
        try:
            d = json.loads(content)
            url_hint = d.get("url", "")[:120] if isinstance(d, dict) else ""
        except Exception:
            pass
        m["content"] = json.dumps({
            "_elided": True,
            "url": url_hint,
            "note": f"content elided (older than {SOFT_ELIDE_AFTER_TURNS} turns; facts already extracted).",
        }, ensure_ascii=False)
        m["_elided"] = True
        elided += 1
    return elided

# --- orchestrator state -----------------------------------------------------

@dataclass
class OrchState:
    anchor: dict
    goal_summary: str
    schema_state: dict = field(default_factory=dict)
    known_facts: list[dict] = field(default_factory=list)
    queries_history: list[str] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    page_cache: dict[str, str] = field(default_factory=dict)
    verify_count: int = 0
    compaction_count: int = 0


# --- main orchestrator loop -------------------------------------------------

async def run_orchestrator(model_key: str, oid: str) -> dict:
    cfg = MODELS[model_key]
    llm = AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"],
                      timeout=httpx.Timeout(ORCH_TIMEOUT_S, connect=10.0), max_retries=2)
    http = httpx.AsyncClient()

    target = load_target(oid)
    anchor = build_anchor(target["org"])
    user_msg = build_initial_user_message(target)

    state = OrchState(
        anchor=anchor,
        goal_summary=f"fill ORG_CARD for {anchor['name']} ({anchor['city']}, address={anchor['address']!r})",
    )

    # Pre-fill yandex_maps section from the data we already have.
    state.schema_state["yandex_maps"] = {
        "rating": target["org"].get("rating"),
        "reviews_count": target["org"].get("reviewsCount"),
        "reviews_sample": [(r.get("text") or "").strip()[:300] for r in (target["reviews"] or []) if (r.get("text") or "").strip()][:6],
        "hours": None,
    }
    state.schema_state["contacts"] = {
        "phones": [{"number": p["number"], "context": "yandex.maps card"} for p in (target["org"].get("phones") or []) if p.get("number")],
        "emails": [],
        "websites": [target["org"]["site"]] if target["org"].get("site") else [],
    }

    messages: list[dict] = [
        {"role": "system", "content": ORCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    trace: list[dict] = []
    submitted_card: dict | None = None

    started = time.time()
    orch_usage = {"prompt": 0, "completion": 0, "last_prompt": 0}
    aux_usage = {"prompt": 0, "completion": 0}
    sub_usage = {"prompt": 0, "completion": 0}
    tool_call_count = {"web_serp": 0, "read_page": 0, "delegate_read": 0,
                       "delegate_verify": 0, "submit_org_card": 0}

    score_cache: dict[str, tuple[float, str]] = {}  # url -> (score, reason) from last SERP

    for turn in range(1, MAX_ORCH_TURNS + 1):
        # Soft-elide before each call
        elided = soft_elide(messages, turn)
        if elided:
            trace.append({"turn": turn, "role": "soft_compact", "elided": elided})

        t0 = time.time()
        try:
            resp = await llm.chat.completions.create(
                model=cfg["model"], messages=_strip_meta(messages), tools=ORCH_TOOLS, tool_choice="auto",
            )
        except Exception as e:
            trace.append({"turn": turn, "role": "error", "content": f"orch LLM call failed: {e!r}"[:500]})
            break
        elapsed = time.time() - t0

        u = getattr(resp, "usage", None)
        if u:
            pt = getattr(u, "prompt_tokens", 0) or 0
            ct = getattr(u, "completion_tokens", 0) or 0
            orch_usage["prompt"] += pt
            orch_usage["completion"] += ct
            orch_usage["last_prompt"] = pt
        msg = resp.choices[0].message
        tcs = getattr(msg, "tool_calls", None) or []

        asst_rec: dict = {"role": "assistant", "content": msg.content or ""}
        if tcs:
            asst_rec["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ]
        messages.append(asst_rec)
        trace.append({
            "turn": turn, "role": "assistant",
            "content": (msg.content or "")[:600],
            "tool_calls": [{"name": tc.function.name, "args": tc.function.arguments[:400]} for tc in tcs],
            "elapsed_s": round(elapsed, 2),
            "orch_prompt_tokens": orch_usage["last_prompt"],
        })

        # Auto-compaction check BEFORE executing tools (we just got the latest prompt_tokens)
        if orch_usage["last_prompt"] >= TOKEN_BUDGET and state.compaction_count < MAX_COMPACTIONS:
            trace.append({"turn": turn, "role": "compact_trigger",
                          "last_prompt_tokens": orch_usage["last_prompt"],
                          "compaction_n": state.compaction_count + 1})
            messages = await compact_context(llm, cfg["model"], messages, state, usage_counter=aux_usage)
            # After compaction we still want to execute the pending tool calls if any? No —
            # the assistant message we just appended includes tool_calls, but after compaction
            # we threw it away. To stay valid we re-run the loop iteration: skip tool execution
            # this turn.
            continue

        # No tools called → stop (model talking) unless on first turn
        if not tcs:
            trace.append({"turn": turn, "role": "note", "content": "Model did not call any tool — stopping."})
            break

        # Execute each tool call
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
                raw = await web_serp_call(http, q, k=k)
                scored = await score_urls_via_llm(
                    llm, cfg["model"], state.anchor, state.goal_summary, raw, state.visited_urls,
                    usage_counter=aux_usage,
                )
                # Cache scores for later self/delegate-read calls (sanity check)
                for r in scored:
                    if r.get("url"):
                        score_cache[r["url"]] = (r.get("score", 5.0), r.get("reason", ""))
                # Return to orch
                result: Any = {"query": q, "count": len(scored), "results": [
                    {"url": r["url"], "title": r["title"][:140], "snippet": r["snippet"][:200],
                     "score": r.get("score"), "reason": r.get("reason")}
                    for r in scored if r.get("url")
                ]}

            elif name == "read_page":
                url = args.get("url", "")
                state.visited_urls.add(url)
                page = await fetch_url(http, url)
                if page.get("text"):
                    state.page_cache[url] = page["text"]
                # Append source if not present
                state.schema_state.setdefault("sources", [])
                if not any(s.get("url") == url for s in state.schema_state["sources"]):
                    state.schema_state["sources"].append({"url": url, "what_it_provided": "self-read"})
                result = page

            elif name == "delegate_read":
                url = args.get("url", "")
                gap = args.get("gap", "")
                state.visited_urls.add(url)
                page_for_cache = await fetch_url(http, url, max_chars=12000)
                if page_for_cache.get("text"):
                    state.page_cache[url] = page_for_cache["text"]
                sub = await delegate_read_call(
                    llm, cfg["model"], http, state, url, gap, usage_counter=sub_usage,
                )
                # Apply fills into state (merge)
                fills = sub.get("fills") or {}
                _merge_fills_into_schema(state.schema_state, fills, source_url=url)
                # Append new facts
                for f in sub.get("new_facts") or []:
                    fdict = {"claim": f.get("claim", ""), "confidence": f.get("confidence"),
                             "source": url}
                    state.known_facts.append(fdict)
                state.schema_state.setdefault("sources", [])
                if not any(s.get("url") == url for s in state.schema_state["sources"]):
                    state.schema_state["sources"].append({
                        "url": url,
                        "what_it_provided": "dead_end" if sub.get("dead_end") else f"delegated read ({len(fills)} fields)",
                    })
                result = sub

            elif name == "delegate_verify":
                claim = args.get("claim", "")
                urls = args.get("urls") or []
                if state.verify_count >= MAX_VERIFY_CALLS:
                    result = {"error": f"max {MAX_VERIFY_CALLS} verify calls used"}
                else:
                    state.verify_count += 1
                    result = await delegate_verify_call(
                        llm, cfg["model"], state, claim, urls, usage_counter=sub_usage,
                    )

            elif name == "submit_org_card":
                submitted_card = args.get("card") or args
                result = {"submitted": True}

            else:
                result = {"error": f"unknown tool {name}"}

            t_elapsed = time.time() - tt
            msg_content = json.dumps(result, ensure_ascii=False)
            # web_serp / read_page produce big payloads; we cap a bit so chat doesn't explode
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": name,
                "content": msg_content[:8000],
                "_turn": turn,
            })
            trace.append({
                "turn": turn, "role": "tool", "tool_name": name,
                "args": json.dumps(args, ensure_ascii=False)[:400],
                "result_preview": msg_content[:500],
                "elapsed_s": round(t_elapsed, 2),
            })

        if submitted_card is not None:
            break

        # Token budget guard AFTER tool execution: if we'd be over budget next round,
        # compact now (the next call would otherwise spike).
        # We approximate next prompt_tokens by adding our payload sizes; if last_prompt
        # is already >= 80% of budget, force compact.
        if (orch_usage["last_prompt"] >= int(TOKEN_BUDGET * 0.85)
                and state.compaction_count < MAX_COMPACTIONS
                and submitted_card is None):
            trace.append({"turn": turn, "role": "compact_trigger_post",
                          "last_prompt_tokens": orch_usage["last_prompt"],
                          "compaction_n": state.compaction_count + 1})
            messages = await compact_context(llm, cfg["model"], messages, state, usage_counter=aux_usage)

    # If never submitted and we're out of turns, force a final submit from accumulated state.
    if submitted_card is None:
        submitted_card = {"_force_submit": True, "card_from_state": state.schema_state}
        trace.append({"turn": "post", "role": "note", "content": "Forced submit from schema_state on exit."})

    await http.aclose()
    total_elapsed = time.time() - started

    return {
        "model": model_key,
        "model_id": cfg["model"],
        "oid": oid,
        "anchor": anchor,
        "elapsed_s": round(total_elapsed, 1),
        "turns": len([t for t in trace if t.get("role") == "assistant"]),
        "tool_call_counts": tool_call_count,
        "compactions": state.compaction_count,
        "verify_used": state.verify_count,
        "tokens": {
            "orch": orch_usage,
            "aux_scoring": aux_usage,
            "subagent": sub_usage,
            "grand_total": (orch_usage["prompt"] + orch_usage["completion"] +
                             aux_usage["prompt"] + aux_usage["completion"] +
                             sub_usage["prompt"] + sub_usage["completion"]),
        },
        "submitted_card": submitted_card,
        "final_schema_state": state.schema_state,
        "known_facts": state.known_facts,
        "queries_history": state.queries_history,
        "visited_urls": sorted(state.visited_urls),
        "trace": trace,
    }


def _merge_fills_into_schema(schema: dict, fills: dict, *, source_url: str) -> None:
    """Merge sub-agent's flat 'fills' dict into the orchestrator's schema_state."""
    if not fills:
        return
    if fills.get("what_they_do") and not schema.get("what_they_do"):
        schema["what_they_do"] = fills["what_they_do"]
    for key in ("scale_indicators", "tech_stack", "problems_signals"):
        if fills.get(key):
            existing = schema.get(key) or []
            for item in fills[key]:
                if item and item not in existing:
                    existing.append(item)
            schema[key] = existing
    if fills.get("vacancies"):
        existing = schema.get("vacancies") or []
        existing_urls = {v.get("url") for v in existing}
        for v in fills["vacancies"]:
            if v and v.get("url") and v["url"] not in existing_urls:
                existing.append(v)
        schema["vacancies"] = existing
    # social
    social = schema.get("social") or {}
    for sub in ("vk", "telegram", "instagram", "youtube", "linkedin", "habr"):
        sub_key = f"social_{sub}"
        if fills.get(sub_key):
            existing = social.get(sub) or []
            for item in fills[sub_key]:
                if item and item not in existing:
                    existing.append(item)
            social[sub] = existing
    if social:
        schema["social"] = social
    # contacts
    contacts = schema.get("contacts") or {}
    if fills.get("phones"):
        existing = contacts.get("phones") or []
        existing_nums = {p.get("number") for p in existing}
        for p in fills["phones"]:
            if p and p.get("number") and p["number"] not in existing_nums:
                existing.append(p)
        contacts["phones"] = existing
    if fills.get("emails"):
        existing = contacts.get("emails") or []
        existing_addrs = {e.get("address") for e in existing}
        for e in fills["emails"]:
            if e and e.get("address") and e["address"] not in existing_addrs:
                existing.append(e)
        contacts["emails"] = existing
    if fills.get("websites"):
        existing = contacts.get("websites") or []
        for w in fills["websites"]:
            if w and w not in existing:
                existing.append(w)
        contacts["websites"] = existing
    if contacts:
        schema["contacts"] = contacts


# --- runner -----------------------------------------------------------------

async def main() -> int:
    model_key = os.environ.get("MODEL", "local")
    oid = os.environ.get("OID", "226497224828")  # Агат by default
    if model_key not in MODELS:
        print(f"Unknown MODEL={model_key}. Options: {list(MODELS)}")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"orch__{oid}__{model_key}.json"

    print(f"[*] Orchestrator on model={model_key} ({MODELS[model_key]['model']})")
    print(f"[*] OID={oid}, output → {out_path.name}")
    print(f"[*] Budget: {TOKEN_BUDGET} prompt_tokens, max_compactions={MAX_COMPACTIONS}, soft_elide_after={SOFT_ELIDE_AFTER_TURNS} turns")

    result = await run_orchestrator(model_key, oid)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[+] Done in {result['elapsed_s']}s, turns={result['turns']}, "
          f"calls={result['tool_call_counts']}, compactions={result['compactions']}")
    print(f"[+] Tokens: orch={result['tokens']['orch']}, aux={result['tokens']['aux_scoring']}, sub={result['tokens']['subagent']}")
    print(f"[+] Grand total tokens: {result['tokens']['grand_total']}")
    print(f"[+] Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
