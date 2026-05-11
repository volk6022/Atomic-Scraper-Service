"""LangGraph nodes for Research Agent"""

import time
import logging
from typing import Any

from src.actions.research.state import ResearchState, NodeEvent

logger = logging.getLogger(__name__)


def emit_node_event(event: NodeEvent) -> None:
    """Emit a node event for tracing (can be hooked to SSE)"""
    logger.info(f"Node event: {event}")


async def classify_node(state: ResearchState) -> dict:
    """Classify query type and seed initial gaps"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "classify",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {"query": state["query"]},
        }
    )

    from src.infrastructure.external_api.facade import get_extraction_client

    facade = get_extraction_client()

    prompt = f"Classify this query: {state['query']}\nOptions: factoid, comparative, exploratory, decomposable"
    result = await facade.generate(prompt)

    query_type = "exploratory"
    if result and isinstance(result, str):
        if "comparative" in result.lower():
            query_type = "comparative"
        elif "factoid" in result.lower():
            query_type = "factoid"
        elif "decomposable" in result.lower():
            query_type = "decomposable"

    initial_gaps = [f"What is {state['query']}?"]

    emit_node_event(
        {
            "type": "node_exited",
            "node": "classify",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 100,
            "data": {"query_type": query_type},
        }
    )

    return {
        "query_type": query_type,
        "gaps": initial_gaps,
    }


async def plan_node(state: ResearchState) -> dict:
    """Generate gaps (open questions) from current evidence"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "plan",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    from src.infrastructure.external_api.facade import get_extraction_client

    facade = get_extraction_client()

    evidence = (
        "\n".join([f["claim"] for f in state["facts"]])
        if state["facts"]
        else "No evidence yet"
    )
    prompt = f"Generate research questions for: {state['query']}\nCurrent evidence: {evidence[:500]}"
    result = await facade.generate(prompt)

    gaps = state["gaps"]
    if result and isinstance(result, str):
        new_gaps = [g.strip() for g in result.split("\n") if g.strip()]
        gaps = list(set(gaps + new_gaps))[:5]

    emit_node_event(
        {
            "type": "node_exited",
            "node": "plan",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 150,
            "data": {"gaps_count": len(gaps)},
        }
    )

    return {"gaps": gaps}


async def search_node(state: ResearchState) -> dict:
    """Perform web search over gaps"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "search",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    if state["stall_counter"] >= 2:
        return {"candidate_urls": []}

    from src.actions.research.tools import web_search

    all_results = []
    for gap in state["gaps"][:3]:
        results = await web_search.ainvoke({"query": gap, "k": 3})
        all_results.extend(results)

    existing_urls = {c["url"] for c in state["candidate_urls"]}
    new_results = [r for r in all_results if r.get("url") not in existing_urls]

    for r in new_results:
        r["score"] = 0.8

    emit_node_event(
        {
            "type": "node_exited",
            "node": "search",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 200,
            "data": {"new_results": len(new_results)},
        }
    )

    return {"candidate_urls": state["candidate_urls"] + new_results}


async def rank_dedupe_node(state: ResearchState) -> dict:
    """Rank and deduplicate candidate URLs"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "rank_dedupe",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    visited = state["visited_urls"]
    candidates = [c for c in state["candidate_urls"] if c["url"] not in visited]

    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

    from src.actions.research.modes import get_mode_preset

    preset = get_mode_preset(state["mode"])
    candidates = candidates[: preset.search_k]

    new_urls_count = len(candidates)
    stall_counter = state["stall_counter"]
    if new_urls_count == 0 and len(state["candidate_urls"]) > 0:
        stall_counter += 1

    emit_node_event(
        {
            "type": "node_exited",
            "node": "rank_dedupe",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 50,
            "data": {"candidates": len(candidates), "stall_counter": stall_counter},
        }
    )

    return {"candidate_urls": candidates, "stall_counter": stall_counter}


async def scrape_node(state: ResearchState) -> dict:
    """Scrape candidate URLs"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "scrape",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    from src.actions.research.tools import scrape_url
    from src.actions.research.modes import get_mode_preset

    preset = get_mode_preset(state["mode"])

    scraped = []
    visited = set(state["visited_urls"])

    for candidate in state["candidate_urls"][: preset.scrape_concurrency]:
        try:
            result = await scrape_url.ainvoke({"url": candidate["url"]})
            if result.get("success"):
                scraped.append(
                    {
                        "url": candidate["url"],
                        "title": candidate.get("title", ""),
                        "text": result.get("text", ""),
                    }
                )
                visited.add(candidate["url"])
        except Exception as e:
            logger.warning(f"Failed to scrape {candidate['url']}: {e}")

    emit_node_event(
        {
            "type": "node_exited",
            "node": "scrape",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 300,
            "data": {"scraped": len(scraped)},
        }
    )

    return {"visited_urls": visited, "scraped_content": scraped}


async def extract_facts_node(state: ResearchState) -> dict:
    """Extract facts from scraped content"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "extract_facts",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    from src.actions.research.tools import extract_facts

    facts = list(state["facts"])
    citations = list(state["citations"])

    for doc in state.get("scraped_content", []):
        try:
            extracted = await extract_facts.ainvoke({"doc": doc.get("text", "")})
            for fact in extracted:
                if "error" not in fact:
                    facts.append(fact)
                    citations.append(
                        {
                            "url": doc.get("url", ""),
                            "title": doc.get("title", ""),
                            "snippet": doc.get("text", "")[:200],
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to extract facts from {doc.get('url')}: {e}")

    emit_node_event(
        {
            "type": "node_exited",
            "node": "extract_facts",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 250,
            "data": {"facts_extracted": len(facts) - len(state["facts"])},
        }
    )

    return {"facts": facts, "citations": citations}


async def reflect_node(state: ResearchState) -> dict:
    """Evaluate progress and check for termination conditions"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "reflect",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    beast_mode = state["beast_mode"]

    budget_ratio = (
        state["tokens_used"] / state["token_budget"] if state["token_budget"] > 0 else 0
    )

    if budget_ratio >= 0.85:
        beast_mode = True
        logger.warning("Beast mode triggered: 85% token budget reached")

    if time.time() > state["deadline_ts"]:
        beast_mode = True
        logger.warning("Beast mode triggered: deadline reached")

    if state["stall_counter"] >= 2:
        beast_mode = True
        logger.warning("Beast mode triggered: stall detected")

    if state["iteration"] >= state["max_iters"]:
        beast_mode = True
        logger.warning("Beast mode triggered: max iterations reached")

    emit_node_event(
        {
            "type": "node_exited",
            "node": "reflect",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 50,
            "data": {"beast_mode": beast_mode, "budget_ratio": budget_ratio},
        }
    )

    return {"beast_mode": beast_mode, "iteration": state["iteration"] + 1}


async def answer_node(state: ResearchState) -> dict:
    """Synthesize final answer from collected facts"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "answer",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    from src.infrastructure.external_api.facade import get_extraction_client

    facade = get_extraction_client()

    facts_text = (
        "\n".join([f["claim"] for f in state["facts"]])
        if state["facts"]
        else "No facts collected"
    )
    prompt = f"Research question: {state['query']}\n\nFacts:\n{facts_text[:2000]}\n\nProvide a comprehensive answer with citations."

    try:
        result = await facade.generate(prompt)
        answer = result if isinstance(result, str) else "Unable to generate answer"
    except Exception:
        answer = f"Based on the research: {facts_text[:500]}"

    emit_node_event(
        {
            "type": "node_exited",
            "node": "answer",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 300,
            "data": {"answer_length": len(answer)},
        }
    )

    return {"answer_draft": answer}


async def writer_node(state: ResearchState) -> dict:
    """Assemble final research report"""
    emit_node_event(
        {
            "type": "node_entered",
            "node": "writer",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": None,
            "data": {},
        }
    )

    answer = state["answer_draft"] or "No answer generated"

    for i, citation in enumerate(state["citations"], 1):
        answer += f"\n[{i}] {citation.get('title', '')} - {citation.get('url', '')}"

    emit_node_event(
        {
            "type": "completed",
            "node": "writer",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_ms": 100,
            "data": {"task_id": "completed"},
        }
    )

    return {"final_answer": answer}
