"""Taskiq worker for research tasks"""

import logging

from src.infrastructure.queue.broker import broker
from src.api.routers.research import _task_store

logger = logging.getLogger(__name__)


@broker.task
async def execute_research_task(task_id: str):
    """Process a research task via Taskiq"""
    from src.actions.research import execute_research_task as run_task

    logger.info(f"Starting research task: {task_id}")
    await run_task(task_id, _task_store)
    return {"task_id": task_id, "status": "processed"}
