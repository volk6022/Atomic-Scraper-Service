"""Research Agent module - LangGraph orchestration for autonomous research"""

from src.actions.research.modes import get_mode_preset, mode_to_initial_state
from src.actions.research.graph import build_graph
from src.actions.research.state import ResearchState, create_initial_state

__all__ = [
    "get_mode_preset",
    "mode_to_initial_state",
    "build_graph",
    "ResearchState",
    "create_initial_state",
    "execute_research_task",
]

import asyncio
import logging

logger = logging.getLogger(__name__)


async def execute_research_task(task_id: str, _task_store: dict):
    """Execute research task using LangGraph"""
    from src.actions.research.graph import build_graph
    from src.actions.research.state import create_initial_state

    task_data = _task_store.get(task_id)
    if not task_data:
        logger.error(f"Task {task_id} not found in store")
        return

    try:
        mode = task_data.get("mode", "balanced")
        query = task_data.get("query")

        graph = build_graph(mode)
        initial_state = create_initial_state(query, mode)

        result = await graph.ainvoke(initial_state)

        _task_store[task_id] = {
            **task_data,
            "status": "completed",
            "result": result,
            "updated_at": asyncio.get_event_loop().time(),
        }
        logger.info(f"Task {task_id} completed successfully")
    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        _task_store[task_id] = {
            **task_data,
            "status": "failed",
            "error": str(e),
        }
