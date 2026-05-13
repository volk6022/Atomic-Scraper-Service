"""Taskiq task for research execution"""

import logging
from datetime import datetime
from src.infrastructure.queue.broker import broker

logger = logging.getLogger(__name__)


@broker.task
async def execute_research_task(task_id: str):
    """Taskiq task that executes the research graph"""
    from src.actions.research.graph import build_graph
    from src.actions.research.state import create_initial_state
    from src.infrastructure.tasks.research_store import get_task, set_task

    logger.info(f"Starting research task: {task_id}")

    task_data = get_task(task_id)
    if not task_data:
        set_task(task_id, {"status": "failed", "error": "Task not found"})
        return {"task_id": task_id, "status": "failed"}

    try:
        mode = task_data.get("mode", "balanced")
        graph = build_graph(mode)
        initial_state = create_initial_state(task_data["query"], mode)

        result = await graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": task_id}}
        )

        set_task(
            task_id,
            {
                "status": "completed",
                "result": result,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        logger.info(f"Research task completed: {task_id}")
        return {"task_id": task_id, "status": "completed"}
    except Exception as e:
        logger.error(f"Research task failed: {task_id} - {e}")
        set_task(
            task_id,
            {
                "status": "failed",
                "error": str(e),
                "updated_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        return {"task_id": task_id, "status": "failed"}
