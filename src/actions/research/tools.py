"""LangChain tool wrappers for the Research Agent.

`extract_facts` (decorated) — the original regex heuristic, kept as a fallback
when the LLM extractor fails or returns nothing.
`extract_facts_llm`        — LLM-driven JSON extraction. Not a LangChain @tool
                              because the agent calls it directly, not via the
                              tool dispatcher.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def web_search(query: str, k: int = 5) -> list[dict]:
    """Web search via local SearXNG (backed by `SearXngSearchClient`).

    On failure returns `[]` (not an error dict) so callers don't have to
    special-case error sentinels mixed in with real results.
    """
    from src.core.logging import get_logger
    from src.domain.models.requests import SearchRequest
    from src.infrastructure.external_api.search_client import search_client

    log = get_logger(__name__)
    try:
        request = SearchRequest(q=query, num=k)
        response = await search_client.search(request)
        return [
            {"url": r.link, "title": r.title, "snippet": r.snippet}
            for r in response.organic
        ]
    except Exception as e:
        log.error("web_search failed for %r: %s", query, e)
        return []


@tool
async def scrape_url(url: str) -> dict:
    """Scrape a URL via SiteEnrichAction and return cleaned text."""
    from src.actions.site_enricher import SiteEnrichAction

    action = SiteEnrichAction()
    try:
        result = await action.execute(url)
        return {
            "url": url,
            "text": result.text,
            "word_count": len(result.text.split()),
            "success": True,
        }
    except Exception as e:
        logger.warning("scrape_url failed %s: %s", url, e)
        return {"url": url, "error": str(e), "success": False}


@tool
async def extract_facts(
    doc: str, focus: Optional[str] = None, source_url: Optional[str] = None
) -> list[dict]:
    """Regex-based fact extraction. Used as a fallback when the LLM extractor
    yields nothing. Picks sentences with digits/percentages/prices since those
    are statistically the most "fact-like" in unstructured prose.
    """
    if not doc:
        return [{"error": "Empty document"}]

    facts = []
    sentences = re.split(r"[.!?]\s+", doc)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20 or len(sentence) > 500:
            continue

        if re.search(r"\d+[%€$£]|\d{4}-\d{2}|\$\d+|€\d+|\d+\.\d+", sentence):
            confidence = 0.7
        elif re.search(r"\d+", sentence):
            confidence = 0.5
        else:
            continue

        if focus and focus.lower() not in sentence.lower():
            continue

        facts.append({
            "claim": sentence[:200],
            "confidence": confidence,
            "source_url": source_url or "extracted",
        })
    return facts[:10]


async def extract_facts_llm(
    doc: str, focus: Optional[str] = None, source_url: Optional[str] = None
) -> list[dict]:
    """LLM-driven fact extraction. Returns up to 8 facts as
    ``[{"claim": str, "confidence": float, "source_url": str}, ...]``.

    Truncates the input doc to ~4 KB — reasoning models are slow on long
    contexts and we already chunk by document.
    """
    from src.actions.research.llm_utils import extract_json
    from src.infrastructure.external_api.facade import get_orchestration_client

    if not doc or not doc.strip():
        return []

    client = get_orchestration_client()
    system = (
        "Extract factual claims from the supplied document. Respond ONLY with "
        "a JSON array of objects: "
        '[{"claim": "...", "confidence": 0.0-1.0}, ...]. '
        "Max 8 items. Drop opinions and marketing fluff. No prose around the JSON."
    )
    focus_line = f"Focus area: {focus}\n\n" if focus else ""
    prompt = f"{focus_line}Document:\n\n{doc[:4000]}"

    try:
        raw = await client.generate(prompt=prompt, system_prompt=system)
    except Exception as e:
        logger.warning("extract_facts_llm LLM call failed: %s", e)
        return []

    parsed = extract_json(raw or "")
    items: list[dict] = []
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        for key in ("facts", "claims", "items"):
            v = parsed.get(key)
            if isinstance(v, list):
                items = v
                break

    out: list[dict] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        claim = (item.get("claim") or "").strip()
        if not claim:
            continue
        try:
            conf = float(item.get("confidence", 0.6))
        except (TypeError, ValueError):
            conf = 0.6
        conf = max(0.0, min(1.0, conf))
        out.append({
            "claim": claim[:500],
            "confidence": conf,
            "source_url": source_url or "extracted",
        })
    return out
