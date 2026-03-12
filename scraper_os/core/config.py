"""
core/config.py — Pydantic Settings for the Scraper OS application.

Manages server-side proxy pool, session timeouts, Redis connection,
and browser defaults. All values can be overridden via environment
variables or a .env file.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Central application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCRAPER_",
        case_sensitive=False,
    )

    # ── Redis ────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL used by Taskiq broker and Pub/Sub.",
    )

    # ── Stateless Pool: Server-side proxy rotation ───────────────────
    serper_proxies: List[str] = Field(
        default_factory=list,
        description=(
            "List of proxy URLs for the stateless scraper pool. "
            "Format: http://user:pass@host:port or socks5://user:pass@host:port. "
            "Empty list means direct connection (no proxy)."
        ),
    )

    # ── Stateful Sessions ────────────────────────────────────────────
    session_timeout_seconds: int = Field(
        default=300,
        ge=30,
        description=(
            "Max idle time (seconds) before a stateful actor force-kills "
            "its browser and exits. Prevents resource leaks from abandoned sessions."
        ),
    )
    session_max_duration_seconds: int = Field(
        default=3600,
        ge=60,
        description="Absolute max lifetime for any session, regardless of activity.",
    )

    # ── Browser Defaults ─────────────────────────────────────────────
    browser_headless: bool = Field(
        default=True,
        description="Default headless mode for Playwright browsers.",
    )
    default_viewport_width: int = Field(default=1920, ge=320)
    default_viewport_height: int = Field(default=1080, ge=240)
    default_user_agent: Optional[str] = Field(
        default=None,
        description="Default User-Agent. None = Playwright default.",
    )

    # ── Taskiq Workers ───────────────────────────────────────────────
    stateless_workers_count: int = Field(
        default=2,
        ge=1,
        description="Number of Taskiq worker processes for the stateless pool.",
    )

    # ── LLM / External Services ──────────────────────────────────────
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for structured output / decision-making.",
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Override OpenAI base URL (for compatible proxies).",
    )
    jina_api_url: Optional[str] = Field(
        default=None,
        description="Jina Reader V2 HuggingFace Endpoint URL.",
    )
    jina_api_key: Optional[str] = Field(
        default=None,
        description="Auth token for Jina endpoint.",
    )
    omni_parser_url: Optional[str] = Field(
        default=None,
        description="Omni-Parser endpoint URL for visual element detection.",
    )

    # ── Proxy rotation helper ────────────────────────────────────────
    _proxy_index: int = 0

    def next_proxy(self) -> Optional[str]:
        """Round-robin proxy selection from the server-side pool.

        Returns None if the proxy list is empty (direct connection).
        """
        if not self.serper_proxies:
            return None
        proxy = self.serper_proxies[self._proxy_index % len(self.serper_proxies)]
        self._proxy_index += 1
        return proxy


# Singleton — import this everywhere
settings = Settings()
