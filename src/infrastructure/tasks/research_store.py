"""In-memory task store for research tasks"""

from typing import Optional

_task_store: dict = {}


def get_task(task_id: str) -> Optional[dict]:
    """Get research task from store"""
    return _task_store.get(task_id)


def set_task(task_id: str, data: dict) -> None:
    """Set research task in store"""
    _task_store[task_id] = data


def get_concurrent_task_count(api_key: str) -> int:
    """Get number of running tasks for an API key"""
    return sum(1 for t in _task_store.values() if t.get("status") == "running")
