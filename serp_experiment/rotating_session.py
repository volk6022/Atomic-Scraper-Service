"""Rotating session manager for reusing Google sessions with solved captcha.

Каждая сессия — папка `sessions/<timestamp>/` со следующими файлами:
    storage_state.json   — native Playwright storage state (cookies+localStorage)
    metadata.json        — { proxy_url, created_at, notes }
    screenshot.png       — опционально, для глазной проверки

`load_sessions()` отбрасывает протухшие (> MAX_AGE_MINUTES) и оставляет до
MAX_SESSIONS свежайших по mtime метаданных.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


MAX_SESSIONS = 10
MAX_AGE_MINUTES = 30


class RotatingSessionManager:
    def __init__(self, sessions_dir: str | Path = "sessions") -> None:
        self.sessions_dir = Path(sessions_dir)
        self._sessions: list[dict[str, Any]] = []
        self._current_index: int = 0

    def load_sessions(self) -> int:
        self._sessions = []
        self._current_index = 0

        if not self.sessions_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(minutes=MAX_AGE_MINUTES)

        valid: list[dict[str, Any]] = []
        for folder in self.sessions_dir.iterdir():
            if not folder.is_dir():
                continue

            metadata_path = folder / "metadata.json"
            storage_state_path = folder / "storage_state.json"
            if not metadata_path.exists() or not storage_state_path.exists():
                continue

            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                created_str = metadata.get("created_at", "")
                if not created_str:
                    continue
                created_at = datetime.fromisoformat(created_str)
                if created_at < cutoff:
                    continue
            except Exception:
                continue

            valid.append({
                "path": str(folder),
                "storage_state_path": str(storage_state_path),
                "proxy_url": metadata.get("proxy_url"),
                "created_at": created_str,
                "notes": metadata.get("notes", ""),
            })

        # newest first, keep MAX_SESSIONS freshest
        valid.sort(key=lambda s: s["created_at"], reverse=True)
        self._sessions = valid[:MAX_SESSIONS]
        return len(self._sessions)

    def get_current_session(self) -> dict[str, Any] | None:
        if not self._sessions:
            return None
        return self._sessions[self._current_index]

    def next_session(self) -> None:
        if self._sessions:
            self._current_index = (self._current_index + 1) % len(self._sessions)

    def get_all_sessions(self) -> list[dict[str, Any]]:
        return list(self._sessions)

    @property
    def session_count(self) -> int:
        return len(self._sessions)
