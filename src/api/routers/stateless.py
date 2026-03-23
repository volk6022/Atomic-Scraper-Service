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
async def scrape(request: ScrapeRequest):
    try:
        context = await pool_manager.create_context(
            proxy={"server": request.proxy} if request.proxy else None
        )
        page = await context.new_page()
        await page.goto(str(request.url), wait_until=request.wait_until)  # type: ignore
        content = await page.content()
        await context.close()
        return ScrapeResponse(
            url=str(request.url), content=content, status=TaskStatus.SUCCESS
        )
    except Exception as e:
        return ScrapeResponse(
            url=str(request.url), status=TaskStatus.FAILED, error=str(e)
        )


@router.post("/serper", response_model=SearchResponse)
async def serper(request: SearchRequest):
    return await search_client.search(request)


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
