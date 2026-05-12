"""Research Agent API endpoints"""

import uuid
import logging
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.domain.models.research import (
    ResearchRequest,
    ResearchTaskCreateResponse,
    ResearchTaskStatus,
    ResearchReport,
)
from src.api.auth import get_api_key
from src.core.config import settings
from src.infrastructure.queue.research_worker import execute_research_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

_task_store: dict = {}


async def get_concurrent_task_count(api_key: str) -> int:
    """Get number of running tasks for an API key"""
    return sum(1 for t in _task_store.values() if t.get("status") == "running")


async def get_research_task(task_id: str) -> Optional[dict]:
    """Get research task from store"""
    return _task_store.get(task_id)


async def set_research_task(task_id: str, data: dict) -> None:
    """Set research task in store"""
    _task_store[task_id] = data


@router.post(
    "/run",
    response_model=ResearchTaskCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_research(
    request: ResearchRequest,
    api_key: str = Depends(get_api_key),
):
    """Submit a new research task"""
    concurrent = await get_concurrent_task_count(api_key)
    if concurrent >= settings.MAX_CONCURRENT_RESEARCH_TASKS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {settings.MAX_CONCURRENT_RESEARCH_TASKS} concurrent tasks allowed",
        )

    task_id = str(uuid.uuid4())

    _task_store[task_id] = {
        "task_id": task_id,
        "query": request.query,
        "mode": request.mode,
        "status": "running",
        "phase": "starting",
        "iteration": 0,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }

    execute_research_task.kiq(task_id)

    return ResearchTaskCreateResponse(
        task_id=task_id,
        status="pending",
        message="Research task queued",
    )


@router.get("/status/{task_id}", response_model=ResearchTaskStatus)
async def get_research_status(
    task_id: str,
    api_key: str = Depends(get_api_key),
):
    """Get status of a research task"""
    task = await get_research_task(task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or expired",
        )

    if task.get("status") == "completed" and task.get("result"):
        return ResearchTaskStatus(
            task_id=task_id,
            status="completed",
            result=ResearchReport(**task["result"]),
            created_at=task["created_at"],
            updated_at=task.get("updated_at"),
        )

    return ResearchTaskStatus(
        task_id=task_id,
        status=task.get("status", "running"),
        progress={
            "phase": task.get("phase", "unknown"),
            "percent": min(task.get("iteration", 0) * 10, 100),
            "message": f"Iteration {task.get('iteration', 0)}",
        },
        created_at=task["created_at"],
        updated_at=task.get("updated_at"),
    )


@router.get("/stream/{task_id}")
async def stream_research_events(
    task_id: str,
    api_key: str = Depends(get_api_key),
):
    """Stream SSE events for a research task"""
    task = await get_research_task(task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or expired",
        )

    async def event_generator():
        yield f"event: started\ndata: {task_id}\n\n"
        yield f"event: progress\ndata: {{'phase': 'running'}}\n\n"

        while True:
            await asyncio.sleep(2)
            task = await get_research_task(task_id)
            if not task:
                break

            if task.get("status") == "completed":
                yield f"event: completed\ndata: {task_id}\n\n"
                break

            yield f"event: progress\ndata: {{'iteration': {task.get('iteration', 0)}}}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
