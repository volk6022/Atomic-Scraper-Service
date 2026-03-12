"""
api/routers/stateless.py — REST endpoints for Circuit A (Stateless Pool).

Provides fast, atomic scraping and searching.
"""

from fastapi import APIRouter, HTTPException
from scraper_os.domain.models.requests import ScrapeRequest, SerperSearchRequest
from scraper_os.domain.models.dsl import ScrapeResult, SerperResult
from scraper_os.infrastructure.queue.pool_workers import scrape_task, serper_task

router = APIRouter(tags=["stateless"])


@router.post("/scraper", response_model=ScrapeResult)
async def scrape(request: ScrapeRequest):
    """Execute an atomic scrape task and wait for the result."""
    task = await scrape_task.kiq(request)
    result = await task.wait_result()
    return result.return_value


@router.post("/serper", response_model=SerperResult)
async def serper(request: SerperSearchRequest):
    """Execute a search task and wait for the result."""
    task = await serper_task.kiq(request)
    result = await task.wait_result()
    return result.return_value
