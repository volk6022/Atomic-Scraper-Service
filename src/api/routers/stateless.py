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
from src.api.auth import get_api_key
import uuid

router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/scraper", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    try:
        context = await pool_manager.create_context(
            proxy={"server": request.proxy} if request.proxy else None
        )
        page = await context.new_page()
        await page.goto(str(request.url), wait_until=request.wait_until)
        content = await page.content()
        await context.close()
        return ScrapeResponse(
            id=str(uuid.uuid4()),
            url=str(request.url),
            content=content,
            status=TaskStatus.SUCCESS,
        )
    except Exception as e:
        return ScrapeResponse(
            id=str(uuid.uuid4()),
            url=str(request.url),
            status=TaskStatus.FAILED,
            error=str(e),
        )


@router.post("/serper", response_model=SearchResponse)
async def search(request: SearchRequest):
    return await search_client.search(request)


@router.post("/omni-parse")
async def omni_parse(request: OmniParseRequest):
    # Integration with LLMFacade would happen here
    return {"elements": []}


@router.post("/jina-extract")
async def jina_extract(request: JinaExtractRequest):
    # Integration with Jina API would happen here
    return {"content": "", "extracted_data": {}}
