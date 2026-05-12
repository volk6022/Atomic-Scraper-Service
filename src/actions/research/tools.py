"""LangChain tool wrappers for Research Agent - reusing existing services"""

from typing import Optional
from langchain_core.tools import tool


class SearchHit:
    """Simple search result from web search"""

    def __init__(self, url: str, title: str, snippet: str):
        self.url = url
        self.title = title
        self.snippet = snippet


@tool
async def web_search(query: str, k: int = 5) -> list[dict]:
    """
    Perform a web search using Google SERP via real browser search.

    Args:
        query: Search query string
        k: Number of results to return (default 5)

    Returns:
        List of search results with url, title, and snippet
    """
    from src.infrastructure.external_api.search_client import search_client
    from src.domain.models.requests import SearchRequest
    from src.core.logging import get_logger

    logger = get_logger(__name__)

    try:
        request = SearchRequest(q=query, num=k)
        response = await search_client.search(request)

        return [
            {
                "url": r.link,
                "title": r.title,
                "snippet": r.snippet,
            }
            for r in response.organic
        ]
    except Exception as e:
        logger.error(f"Web search failed for '{query}': {e}")
        return [{"error": str(e)}]


@tool
async def scrape_url(url: str) -> dict:
    """
    Scrape a URL and extract clean text content.

    Args:
        url: URL to scrape

    Returns:
        Dict with text content and metadata
    """
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
        return {
            "url": url,
            "error": str(e),
            "success": False,
        }


@tool
async def extract_facts(
    doc: str, focus: Optional[str] = None, source_url: Optional[str] = None
) -> list[dict]:
    """
    Extract factual claims from document text using heuristic extraction.

    Args:
        doc: Document text to analyze
        focus: Optional focus area (e.g., "pricing", "features")
        source_url: Optional source URL for attribution

    Returns:
        List of extracted facts with claim, confidence, source
    """
    import re

    if not doc:
        return [{"error": "Empty document"}]

    facts = []
    sentences = re.split(r"[.!?]\s+", doc)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) < 20 or len(sentence) > 500:
            continue

        if re.search(r"\d+[%€$£]|\d{4}-\d{2}|\$\d+|€\d+|\d+\.\d+", sentence):
            confidence = 0.7
        elif re.search(r"\d+", sentence):
            confidence = 0.5
        else:
            continue

        if focus and focus.lower() not in sentence.lower():
            continue

        facts.append(
            {
                "claim": sentence[:200],
                "confidence": confidence,
                "source_url": source_url or "extracted",
            }
        )

    return facts[:10]
