"""Shared session helpers for Playwright-based approaches.

Используем нативный Playwright `storage_state` (cookies + localStorage per
origin) — он восстанавливает состояние атомарно при создании контекста, без
танцев с goto/about:blank/evaluate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def session_storage_state_path(session: dict[str, Any] | None) -> str | None:
    """Return absolute path to storage_state.json for given session, or None."""
    if not session:
        return None
    base = session.get("path")
    if not base:
        return None
    p = Path(base) / "storage_state.json"
    if not p.exists():
        return None
    return str(p)
