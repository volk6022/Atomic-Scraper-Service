"""LangGraph nodes for Research Agent.

Major behaviours worth knowing (non-obvious, do not remove without checking):
- The orchestration LLM is a reasoning model that emits `<think>...</think>`
  blocks. All LLM-driven nodes route raw output through `llm_utils.strip_reasoning`
  before any keyword/JSON parsing.
- `search_node` no longer returns `[]` on the stall path — that would wipe the
  candidate list (LangGraph default reducer = overwrite). It returns the
  existing list unchanged so downstream nodes can still scrape what we have.
- `rank_dedupe_node` keeps the full candidate pool intact and emits a separate
  `current_batch` of top-K unvisited candidates that `scrape_node` consumes.
- `extract_facts_node` uses the LLM (with JSON output + retry-on-empty fallback
  to the regex heuristic) — not the bare regex tool.
- `writer_node` produces a `ResearchReport`-compatible dict in `final_report`
  (query/mode/answer_markdown/citations/facts/stats) so the API contract holds.
- Citations are deduplicated by URL.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from src.actions.research.state import ResearchState, NodeEvent
from src.actions.research.llm_utils import extract_json, strip_reasoning

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_node_event(event: NodeEvent) -> None:
    logger.info(f"Node event: {event}")


async def classify_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "classify",
        "timestamp": _now_iso(), "elapsed_ms": None,
        "data": {"query": state["query"]},
    })

    from src.infrastructure.external_api.facade import get_orchestration_client

    client = get_orchestration_client()
    system = (
        "You are a query classifier. Respond with a single JSON object "
        '{"type": "<factoid|comparative|exploratory|decomposable>"} and nothing else.'
    )
    prompt = f"Classify this query: {state['query']}"
    query_type = "exploratory"
    try:
        result = await client.generate(prompt=prompt, system_prompt=system)
        parsed = extract_json(result or "")
        if isinstance(parsed, dict):
            value = str(parsed.get("type", "")).lower().strip()
            if value in ("factoid", "comparative", "exploratory", "decomposable"):
                query_type = value
        else:
            cleaned = strip_reasoning(result or "").lower()
            for candidate in ("comparative", "decomposable", "factoid", "exploratory"):
                if candidate in cleaned:
                    query_type = candidate
                    break
    except Exception as e:
        logger.warning("classify_node LLM failed, defaulting to exploratory: %s", e)

    emit_node_event({
        "type": "node_exited", "node": "classify",
        "timestamp": _now_iso(), "elapsed_ms": 100,
        "data": {"query_type": query_type},
    })
    return {
        "query_type": query_type,
        "gaps": [state["query"]],
    }


async def plan_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "plan",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    from src.infrastructure.external_api.facade import get_orchestration_client

    client = get_orchestration_client()
    evidence = (
        "\n".join(f"- {f['claim']}" for f in state["facts"][:30])
        if state["facts"]
        else "No evidence yet"
    )
    system = (
        "You generate concise research sub-questions. Respond ONLY with a JSON "
        'array of 3-5 strings: ["question 1", "question 2", ...]. No prose, '
        "no numbering, no explanation."
    )
    prompt = (
        f"Main question: {state['query']}\n\n"
        f"Evidence so far:\n{evidence[:1200]}\n\n"
        "List 3-5 open sub-questions that, if answered, would let us answer the main question."
    )

    new_gaps: list[str] = []
    try:
        result = await client.generate(prompt=prompt, system_prompt=system)
        parsed = extract_json(result or "")
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str) and 5 <= len(item.strip()) <= 200:
                    new_gaps.append(item.strip())
        elif isinstance(parsed, dict):
            # Some models wrap in {"questions": [...]} despite the prompt.
            for key in ("questions", "gaps", "items"):
                v = parsed.get(key)
                if isinstance(v, list):
                    new_gaps.extend(
                        s.strip() for s in v if isinstance(s, str) and 5 <= len(s.strip()) <= 200
                    )
                    break
    except Exception as e:
        logger.warning("plan_node LLM failed: %s", e)

    # Preserve insertion order, dedupe, cap at 5 (keep prior gaps too).
    merged: list[str] = []
    seen = set()
    for g in state["gaps"] + new_gaps:
        norm = g.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            merged.append(g.strip())
    gaps = merged[:5]

    emit_node_event({
        "type": "node_exited", "node": "plan",
        "timestamp": _now_iso(), "elapsed_ms": 150,
        "data": {"gaps_count": len(gaps), "new_gaps": len(new_gaps)},
    })
    return {"gaps": gaps}


async def search_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "search",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    if state["stall_counter"] >= 2:
        emit_node_event({
            "type": "node_exited", "node": "search",
            "timestamp": _now_iso(), "elapsed_ms": 0,
            "data": {"skipped": True, "reason": "stall"},
        })
        return {}  # keep candidate_urls as-is; LangGraph won't overwrite missing keys

    from src.actions.research.tools import web_search

    new_results: list[dict] = []
    existing_urls = {c["url"] for c in state["candidate_urls"] if c.get("url")}
    search_errors = 0

    for gap in state["gaps"][:3]:
        try:
            results = await web_search.ainvoke({"query": gap, "k": 3})
        except Exception as e:
            logger.warning("web_search failed for gap '%s': %s", gap, e)
            search_errors += 1
            continue

        for r in results:
            if not isinstance(r, dict):
                continue
            if r.get("error"):
                search_errors += 1
                continue
            url = r.get("url")
            if not url or url in existing_urls:
                continue
            existing_urls.add(url)
            new_results.append({
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "score": 0.8,
            })

    stall_increment = 1 if not new_results else 0

    emit_node_event({
        "type": "node_exited", "node": "search",
        "timestamp": _now_iso(), "elapsed_ms": 200,
        "data": {"new_results": len(new_results), "errors": search_errors,
                 "stall_inc": stall_increment},
    })

    update: dict = {"candidate_urls": state["candidate_urls"] + new_results}
    if stall_increment:
        update["stall_counter"] = state["stall_counter"] + stall_increment
    return update


async def rank_dedupe_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "rank_dedupe",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    from src.actions.research.modes import get_mode_preset

    preset = get_mode_preset(state["mode"])
    visited = set(state["visited_urls"])

    unvisited = [c for c in state["candidate_urls"] if c["url"] not in visited]
    unvisited.sort(key=lambda x: x.get("score", 0), reverse=True)
    batch = unvisited[: preset.search_k]

    stall_counter = state["stall_counter"]
    if not batch and state["candidate_urls"]:
        stall_counter += 1

    emit_node_event({
        "type": "node_exited", "node": "rank_dedupe",
        "timestamp": _now_iso(), "elapsed_ms": 50,
        "data": {"batch": len(batch), "pool": len(unvisited), "stall_counter": stall_counter},
    })

    # Keep candidate_urls intact; emit current_batch for scrape_node.
    return {"current_batch": batch, "stall_counter": stall_counter}


async def scrape_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "scrape",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    from src.actions.research.tools import scrape_url
    from src.actions.research.modes import get_mode_preset

    preset = get_mode_preset(state["mode"])
    batch = state.get("current_batch") or state["candidate_urls"][: preset.scrape_concurrency]

    sem = asyncio.Semaphore(preset.scrape_concurrency)
    visited = set(state["visited_urls"])

    async def _do(candidate: dict) -> dict | None:
        url = candidate.get("url")
        if not url:
            return None
        async with sem:
            try:
                result = await scrape_url.ainvoke({"url": url})
            except Exception as e:
                logger.warning("scrape failed %s: %s", url, e)
                return None
            if not result.get("success"):
                return None
            return {
                "url": url,
                "title": candidate.get("title", ""),
                "snippet": candidate.get("snippet", ""),
                "text": result.get("text", ""),
            }

    results = await asyncio.gather(*[_do(c) for c in batch])
    scraped = [r for r in results if r]
    for doc in scraped:
        visited.add(doc["url"])

    emit_node_event({
        "type": "node_exited", "node": "scrape",
        "timestamp": _now_iso(), "elapsed_ms": 300,
        "data": {"requested": len(batch), "scraped": len(scraped)},
    })

    return {"visited_urls": sorted(visited), "scraped_content": scraped}


async def extract_facts_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "extract_facts",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    from src.actions.research.tools import extract_facts_llm, extract_facts

    facts = list(state["facts"])
    citations = list(state["citations"])
    cited_urls = {c.get("url") for c in citations}

    new_count = 0
    for doc in state.get("scraped_content", []):
        text = doc.get("text", "")
        if not text:
            continue
        source_url = doc.get("url", "")
        try:
            extracted = await extract_facts_llm(
                doc=text, focus=state["query"], source_url=source_url
            )
        except Exception as e:
            logger.warning("LLM fact extraction failed for %s: %s", source_url, e)
            extracted = []

        if not extracted:
            # Heuristic fallback so we still get something usable from each doc.
            try:
                extracted = await extract_facts.ainvoke(
                    {"doc": text, "focus": None, "source_url": source_url}
                )
            except Exception:
                extracted = []

        any_added = False
        for fact in extracted:
            if not isinstance(fact, dict) or "error" in fact:
                continue
            claim = (fact.get("claim") or "").strip()
            if not claim:
                continue
            confidence = float(fact.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            facts.append({
                "claim": claim[:500],
                "confidence": confidence,
                "source_url": source_url or "extracted",
            })
            any_added = True
            new_count += 1

        if any_added and source_url and source_url not in cited_urls:
            cited_urls.add(source_url)
            citations.append({
                "url": source_url,
                "title": doc.get("title", "") or source_url,
                "snippet": (doc.get("snippet") or text[:200]),
            })

    emit_node_event({
        "type": "node_exited", "node": "extract_facts",
        "timestamp": _now_iso(), "elapsed_ms": 250,
        "data": {"facts_extracted": new_count, "citations_total": len(citations)},
    })

    return {"facts": facts, "citations": citations}


async def reflect_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "reflect",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    beast_mode = state["beast_mode"]
    budget_ratio = (
        state["tokens_used"] / state["token_budget"] if state["token_budget"] > 0 else 0
    )

    if budget_ratio >= 0.85:
        beast_mode = True
    if time.time() > state["deadline_ts"]:
        beast_mode = True
    if state["stall_counter"] >= 2:
        beast_mode = True

    iteration = state["iteration"] + 1

    emit_node_event({
        "type": "node_exited", "node": "reflect",
        "timestamp": _now_iso(), "elapsed_ms": 50,
        "data": {"beast_mode": beast_mode, "budget_ratio": budget_ratio,
                 "iteration": iteration},
    })

    return {"beast_mode": beast_mode, "iteration": iteration}


async def answer_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "answer",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    from src.infrastructure.external_api.facade import get_orchestration_client

    client = get_orchestration_client()
    # Index facts by source so we can reference [N].
    citations = state["citations"]
    url_to_index = {c["url"]: i + 1 for i, c in enumerate(citations)}
    fact_lines = []
    for f in state["facts"][:60]:
        idx = url_to_index.get(f.get("source_url", ""), 0)
        ref = f"[{idx}]" if idx else ""
        fact_lines.append(f"- {f['claim']} {ref}".strip())
    facts_text = "\n".join(fact_lines) if fact_lines else "No facts collected"

    system = (
        "You are a research writer. Produce a concise markdown answer with "
        "inline numeric citations like [1], [2] that correspond to the facts. "
        "Do not invent claims that are not in the provided facts."
    )
    prompt = (
        f"Research question: {state['query']}\n\n"
        f"Collected facts:\n{facts_text[:4000]}\n\n"
        "Write the answer."
    )

    try:
        result = await client.generate(prompt=prompt, system_prompt=system)
        answer = strip_reasoning(result or "")
        if not answer:
            answer = f"Based on the research:\n\n{facts_text[:800]}"
    except Exception as e:
        logger.warning("answer_node LLM failed: %s", e)
        answer = f"Based on the research:\n\n{facts_text[:800]}"

    emit_node_event({
        "type": "node_exited", "node": "answer",
        "timestamp": _now_iso(), "elapsed_ms": 300,
        "data": {"answer_length": len(answer)},
    })
    return {"answer_draft": answer}


async def writer_node(state: ResearchState) -> dict:
    emit_node_event({
        "type": "node_entered", "node": "writer",
        "timestamp": _now_iso(), "elapsed_ms": None, "data": {},
    })

    answer = state.get("answer_draft") or "No answer generated."
    citations = state["citations"]

    citation_section = ""
    if citations:
        lines = ["", "## Sources", ""]
        for i, c in enumerate(citations, 1):
            title = (c.get("title") or c.get("url") or "").strip()
            url = c.get("url", "")
            lines.append(f"[{i}] {title} — {url}")
        citation_section = "\n".join(lines)

    answer_markdown = f"{answer}\n{citation_section}".rstrip() + "\n"

    started = state.get("started_ts") or state["deadline_ts"]  # fallback
    elapsed = max(0.0, time.time() - (state.get("started_ts") or time.time()))

    final_report = {
        "query": state["query"],
        "mode": state["mode"],
        "answer_markdown": answer_markdown,
        "citations": [
            {
                "url": c["url"],
                "title": (c.get("title") or c["url"]),
                "snippet": (c.get("snippet") or "")[:500],
            }
            for c in citations
        ],
        "facts": [
            {
                "claim": f["claim"],
                "confidence": float(f.get("confidence", 0.5)),
                "source_url": f.get("source_url") or (citations[0]["url"] if citations else "https://example.com"),
            }
            for f in state["facts"]
            if (f.get("source_url") or "").startswith("http")
        ],
        "stats": {
            "iterations": state["iteration"],
            "urls_visited": len(state["visited_urls"]),
            "elapsed_seconds": round(elapsed, 2),
            "mode_used": state["mode"],
            "beast_mode_triggered": state["beast_mode"],
        },
    }

    emit_node_event({
        "type": "completed", "node": "writer",
        "timestamp": _now_iso(), "elapsed_ms": 100,
        "data": {"answer_length": len(answer_markdown),
                 "citations": len(citations), "facts": len(state["facts"])},
    })

    return {"final_answer": answer_markdown, "final_report": final_report}
