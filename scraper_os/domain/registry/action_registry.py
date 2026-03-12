"""
domain/registry/ — Action Registry pattern.

The registry maps string action names (from CommandPayload.action) to
concrete BaseAction subclasses.  Actions self-register via the
``@register`` decorator, keeping the mapping decoupled from the caller.

Usage
-----
    from scraper_os.domain.registry import action_registry, register

    @register("goto")
    class GotoAction(BaseAction):
        ...

    # Later, in the actor loop:
    action_cls = action_registry.get("goto")
    result = await action_cls().execute(page, params, llm_facade)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from scraper_os.actions.base import BaseAction

logger = logging.getLogger(__name__)


class ActionRegistry:
    """Thread-safe (GIL-level) registry of action name -> class mappings."""

    def __init__(self) -> None:
        self._actions: Dict[str, Type["BaseAction"]] = {}

    def register(self, name: str, action_cls: Type["BaseAction"]) -> None:
        """Register an action class under ``name``.

        Raises ``ValueError`` if the name is already taken (prevents
        silent overwrites during development).
        """
        if name in self._actions:
            raise ValueError(
                f"Action '{name}' is already registered "
                f"({self._actions[name].__qualname__}). "
                f"Cannot re-register with {action_cls.__qualname__}."
            )
        self._actions[name] = action_cls
        logger.debug("Registered action: %s -> %s", name, action_cls.__qualname__)

    def get(self, name: str) -> Type["BaseAction"]:
        """Look up an action class by name.

        Raises ``KeyError`` with a helpful message listing available actions.
        """
        if name not in self._actions:
            available = ", ".join(sorted(self._actions.keys())) or "(none)"
            raise KeyError(f"Unknown action '{name}'. Available actions: {available}")
        return self._actions[name]

    def has(self, name: str) -> bool:
        return name in self._actions

    def list_actions(self) -> list[str]:
        return sorted(self._actions.keys())

    def __len__(self) -> int:
        return len(self._actions)

    def __repr__(self) -> str:
        return f"ActionRegistry({self.list_actions()})"


# ── Global singleton ─────────────────────────────────────────────────
action_registry = ActionRegistry()


def register(name: str):
    """Decorator to register a BaseAction subclass in the global registry.

    Example::

        @register("goto")
        class GotoAction(BaseAction):
            async def execute(self, page, params, llm):
                ...
    """

    def decorator(cls: Type["BaseAction"]) -> Type["BaseAction"]:
        action_registry.register(name, cls)
        return cls

    return decorator
