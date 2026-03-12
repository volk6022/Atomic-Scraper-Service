"""
domain/models/requests.py — Pydantic models for incoming data.

These models define the contracts for REST/WebSocket requests
flowing into the system.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionConfig(BaseModel):
    """Configuration supplied by the client when creating a stateful session.

    The client owns the proxy choice here (unlike stateless pool where
    proxies are managed server-side via round-robin).
    """

    headless: bool = Field(
        default=True,
        description="Run browser in headless mode.",
    )
    proxy: Optional[str] = Field(
        default=None,
        description="Proxy URL. Format: socks5://user:pass@host:port",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Custom User-Agent string.",
    )
    window_size: Dict[str, int] = Field(
        default={"width": 1920, "height": 1080},
        description="Browser viewport dimensions.",
    )


class CommandPayload(BaseModel):
    """A single command sent over WebSocket to a stateful session.

    The ``action`` field is looked up in the ActionRegistry to find the
    concrete handler.  ``params`` carries action-specific arguments.
    """

    action: str = Field(
        ...,
        description="Name of the action from ActionRegistry (e.g. 'goto', 'omni_click').",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific parameters.",
    )


class ScrapeRequest(BaseModel):
    """Payload for the stateless /scrape endpoint."""

    url: str = Field(..., description="Target URL to scrape.")
    wait_for: Optional[str] = Field(
        default=None,
        description="CSS selector to wait for before capturing content.",
    )
    timeout_ms: int = Field(
        default=30_000,
        ge=1_000,
        le=120_000,
        description="Navigation timeout in milliseconds.",
    )
    extract_text: bool = Field(
        default=False,
        description="If True, return innerText instead of full HTML.",
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Extra HTTP headers to set on the browser context.",
    )


class SerperSearchRequest(BaseModel):
    """Payload for the stateless /serper endpoint (search via scraping)."""

    query: str = Field(..., description="Search query string.")
    num_results: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return.",
    )
    search_engine: str = Field(
        default="google",
        description="Search engine to target.",
    )


class SessionCreateRequest(BaseModel):
    """REST request body for POST /sessions."""

    config: SessionConfig = Field(default_factory=SessionConfig)
    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional tags for session identification / filtering.",
    )
