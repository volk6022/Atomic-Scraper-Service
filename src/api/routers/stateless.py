from fastapi import APIRouter, Depends
from src.domain.models.requests import (
    ScrapeRequest,
    ScrapeResponse,
    SearchRequest,
    SearchResponse,
    OmniParseRequest,
    JinaExtractRequest,
    TaskStatus,
)
from src.infrastructure.browser.pool_manager import pool_manager
from src.infrastructure.external_api.search_client import search_client
from src.infrastructure.external_api.facade import (
    get_extraction_client,
    get_orchestration_client,
)
from src.api.auth import get_api_key
import uuid

router = APIRouter(dependencies=[Depends(get_api_key)])
extraction_client = get_extraction_client()
orchestration_client = get_orchestration_client()


@router.post("/scraper", response_model=ScrapeResponse)
# ... (rest of the scrape function remains the same)
@router.post("/omni-parse")
async def omni_parse(request: OmniParseRequest):
    # Use orchestration client for UI grounding tasks
    result = await orchestration_client.generate(
        prompt=f"Analyze this image (base64) for elements: {request.prompt or 'Find all interactive elements'}"
    )
    return {"raw_analysis": result}


@router.post("/jina-extract")
async def jina_extract(request: JinaExtractRequest):
    # Use extraction client (e.g., Jina Reader LM)
    result = await extraction_client.extract(
        content=request.html, schema=request.extraction_schema or {}
    )
    return {"extracted_data": result}
