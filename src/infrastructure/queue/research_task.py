"""Taskiq task that executes the LangGraph research agent."""

import logging
from datetime import datetime, timezone

from src.infrastructure.queue.broker import broker

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@broker.task
async def execute_research_task(task_id: str):
    from src.actions.research.graph import build_graph
    from src.actions.research.state import create_initial_state
    from src.infrastructure.tasks.research_store import get_task, set_task

    logger.info("Starting research task: %s", task_id)

    task_data = get_task(task_id)
    if not task_data:
        set_task(task_id, {"status": "failed", "error": "Task not found",
                           "updated_at": _now_iso()})
        return {"task_id": task_id, "status": "failed"}

    mode = task_data.get("mode", "balanced")
    query = task_data.get("query", "")

    try:
        graph = build_graph(mode)
        initial_state = create_initial_state(query, mode)

        result = await graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": task_id}}
        )

        final_report = result.get("final_report")
        if not final_report:
            raise RuntimeError("Graph finished without a final_report — writer_node bug?")

        set_task(task_id, {
            "status": "completed",
            "phase": "completed",
            "iteration": result.get("iteration", 0),
            "result": final_report,
            "updated_at": _now_iso(),
        })
        logger.info("Research task completed: %s", task_id)
        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        logger.exception("Research task failed: %s", task_id)
        set_task(task_id, {
            "status": "failed",
            "error": str(e),
            "updated_at": _now_iso(),
        })
        return {"task_id": task_id, "status": "failed"}
