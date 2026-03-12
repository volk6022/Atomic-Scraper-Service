"""
domain/models/dsl.py — Response / result models for the DSL command layer.

These models standardize the output that actions produce and that
flows back to clients through Redis Pub/Sub and WebSocket.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionStatus(str, Enum):
    """Outcome status of a single action execution."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class ActionResult(BaseModel):
    """Standardized result returned by every action handler.

    Sent back to the client via Redis ``res:{session_id}`` channel.
    """

    status: ActionStatus = Field(..., description="Outcome of the action.")
    action: str = Field(..., description="Name of the action that was executed.")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Action-specific result payload (HTML, coordinates, etc.).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable error message when status is 'error'.",
    )
    screenshot_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded screenshot taken after action execution.",
    )

    @classmethod
    def ok(
        cls,
        action: str,
        data: Dict[str, Any] | None = None,
        screenshot: str | None = None,
    ) -> "ActionResult":
        return cls(
            status=ActionStatus.OK,
            action=action,
            data=data,
            screenshot_base64=screenshot,
        )

    @classmethod
    def fail(cls, action: str, error: str) -> "ActionResult":
        return cls(status=ActionStatus.ERROR, action=action, error=error)


class ScrapeResult(BaseModel):
    """Result returned by the stateless /scrape endpoint."""

    url: str
    html: Optional[str] = None
    text: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


class SerperResult(BaseModel):
    """Result returned by the stateless /serper endpoint."""

    query: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class SessionInfo(BaseModel):
    """Metadata about an active stateful session."""

    session_id: str
    status: str = Field(default="active", description="active | closing | closed")
    created_at: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class LLMDecision(BaseModel):
    """Structured output from LLM deciding the next action."""

    action: str = Field(
        ..., description="Action to take (goto, click, omni_click, etc.)"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict, description="Parameters for the action"
    )
    reasoning: str = Field(..., description="LLM's thought process or explanation")
