"""
actions/base.py — Abstract base class for all DSL actions.

Every concrete action (navigation, extraction, AI-powered) must
subclass ``BaseAction`` and implement the ``execute`` method.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict

from scraper_os.domain.models.dsl import ActionResult

if TYPE_CHECKING:
    from playwright.async_api import Page


logger = logging.getLogger(__name__)


class BaseAction(ABC):
    """Contract that all actions in the system must follow.

    Attributes
    ----------
    name : str
        Human-readable identifier (set by subclasses or the registry decorator).

    Notes
    -----
    Actions are instantiated per-call (stateless). Any shared state
    should flow through ``params`` or ``llm_facade``.
    """

    name: str = "base"

    @abstractmethod
    async def execute(
        self,
        page: "Page",
        params: Dict[str, Any],
        llm_facade: Any | None = None,
    ) -> ActionResult:
        """Execute the action against a live Playwright page.

        Parameters
        ----------
        page : Page
            The Playwright page instance owned by the session actor.
        params : dict
            Action-specific parameters from ``CommandPayload.params``.
        llm_facade : LLMFacade | None
            Optional LLM facade for AI-powered actions.

        Returns
        -------
        ActionResult
            Standardized result with status, data, and optional screenshot.
        """
        ...

    async def _safe_screenshot(self, page: "Page") -> str | None:
        """Take a base64 screenshot, returning None on failure."""
        try:
            screenshot_bytes = await page.screenshot(type="png")
            import base64

            return base64.b64encode(screenshot_bytes).decode("ascii")
        except Exception as exc:
            logger.warning("Screenshot failed: %s", exc)
            return None
