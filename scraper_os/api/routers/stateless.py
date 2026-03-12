"""
Stateless Router - REST эндпоинты для скрапинга и поиска.

Эндпоинты:
- POST /scraper - Скрапинг URL
- POST /serper - Поисковый запрос
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException

from domain.models import ScraperRequest, SerperRequest
from infrastructure.queue.broker import broker
from infrastructure.queue.pool_workers import scrape_task, serper_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["stateless"])


@router.post("/scraper")
async def scrape_endpoint(request: ScraperRequest) -> dict:
    """
    Скрапинг URL.
    
    Запускает задачу скрапинга через Taskiq и ждёт результат.
    
    Args:
        request: Запрос с URL и опциями
    
    Returns:
        Результат скрапинга (HTML, статус, etc.)
    """
    logger.info(f"Scrape request: {request.url}")
    
    try:
        # Запуск задачи через Taskiq
        task = await scrape_task.kiq(
            url=request.url,
            proxy=request.proxy,
            wait_selector=request.wait_selector,
            wait_timeout=request.wait_timeout,
            user_agent=None,
        )
        
        # Ожидание результата
        result = await task.wait_result(timeout=60)
        
        if result.return_value.get("success"):
            return result.return_value
        else:
            raise HTTPException(
                status_code=500,
                detail=result.return_value.get("error", "Scraping failed"),
            )
            
    except TimeoutError:
        logger.error(f"Scrape timeout: {request.url}")
        raise HTTPException(
            status_code=504,
            detail="Scraping timeout",
        )
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@router.post("/serper")
async def serper_endpoint(request: SerperRequest) -> dict:
    """
    Поисковый запрос.
    
    Запускает задачу поиска через Taskiq и ждёт результат.
    
    Args:
        request: Запрос с query и количеством результатов
    
    Returns:
        Результаты поиска
    """
    logger.info(f"Serper request: {request.query}")
    
    try:
        # Запуск задачи через Taskiq
        task = await serper_task.kiq(
            query=request.query,
            num_results=request.num_results,
            proxy=request.proxy,
        )
        
        # Ожидание результата
        result = await task.wait_result(timeout=60)
        
        if result.return_value.get("success"):
            return result.return_value
        else:
            raise HTTPException(
                status_code=500,
                detail=result.return_value.get("error", "Search failed"),
            )
            
    except TimeoutError:
        logger.error(f"Serper timeout: {request.query}")
        raise HTTPException(
            status_code=504,
            detail="Search timeout",
        )
    except Exception as e:
        logger.error(f"Serper error: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
