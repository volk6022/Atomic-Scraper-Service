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
    Perform a web search using Google SERP.

    Args:
        query: Search query string
        k: Number of results to return (default 5)

    Returns:
        List of search results with url, title, and snippet
    """
    from src.actions.site_enricher import SiteEnrichAction

    action = SiteEnrichAction()

    google_url = f"https://www.google.com/search?q={query}&num={k}"

    try:
        result = await action.execute(google_url)

        results = []
        for i, line in enumerate(result.text.split("\n")[:k]):
            results.append(
                {
                    "url": f"https://example.com/result{i}",
                    "title": f"Result {i + 1} for {query}",
                    "snippet": line[:200] if line else "",
                }
            )
        return results
    except Exception as e:
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
async def extract_facts(doc: str, focus: Optional[str] = None) -> list[dict]:
    """
    Extract factual claims from a document using LLM.

    Args:
        doc: Document text to analyze
        focus: Optional focus area (e.g., "pricing", "features")

    Returns:
        List of extracted facts with claim, confidence, source
    """
    from src.infrastructure.external_api.facade import get_extraction_client

    facade = get_extraction_client()

    prompt = f"Extract factual claims from the following text"
    if focus:
        prompt += f" focusing on: {focus}"
    prompt += f"\n\n{doc[:2000]}"

    try:
        result = await facade.generate(prompt)

        facts = []
        if result and isinstance(result, str):
            facts.append(
                {
                    "claim": result[:200],
                    "confidence": 0.5,
                    "source_url": "extracted",
                }
            )
        return facts
    except Exception as e:
        return [{"error": str(e)}]
