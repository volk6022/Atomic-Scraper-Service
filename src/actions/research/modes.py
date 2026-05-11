"""Research mode presets and state initialization"""

import time
from dataclasses import dataclass
from typing import Optional

from src.domain.models.research import ResearchMode


@dataclass
class ModePreset:
    """Preset configuration for a research mode"""

    max_iters: int
    search_k: int
    scrape_concurrency: int
    token_budget: int
    deadline: float
    scrape_strategy: str


PRESETS: dict[str, ModePreset] = {
    "speed": ModePreset(
        max_iters=2,
        search_k=3,
        scrape_concurrency=2,
        token_budget=30000,
        deadline=120.0,
        scrape_strategy="text-only enrich",
    ),
    "balanced": ModePreset(
        max_iters=6,
        search_k=5,
        scrape_concurrency=3,
        token_budget=100000,
        deadline=300.0,
        scrape_strategy="full enrich + cleaner",
    ),
    "quality": ModePreset(
        max_iters=25,
        search_k=8,
        scrape_concurrency=5,
        token_budget=1000000,
        deadline=1200.0,
        scrape_strategy="full enrich + retry",
    ),
}


def get_mode_preset(mode: str) -> ModePreset:
    """Get the preset configuration for a mode"""
    if mode not in PRESETS:
        raise ValueError(
            f"Invalid mode: {mode}. Must be one of: {list(PRESETS.keys())}"
        )
    return PRESETS[mode]


def mode_to_initial_state(
    query: str,
    mode_str: str,
    preset: ModePreset,
    max_iters_override: Optional[int] = None,
    max_tokens_override: Optional[int] = None,
) -> dict:
    """Convert mode preset to initial LangGraph state"""
    max_iters = max_iters_override if max_iters_override else preset.max_iters
    max_tokens = max_tokens_override if max_tokens_override else preset.token_budget

    if max_iters_override is not None and (max_iters < 1 or max_iters > 20):
        raise ValueError("max_iters must be between 1 and 20")
    if max_tokens_override is not None and (max_tokens < 1000 or max_tokens > 32000):
        raise ValueError("max_tokens must be between 1000 and 32000")

    return {
        "query": query,
        "mode": mode_str,
        "max_iters": max_iters,
        "max_tokens": max_tokens,
        "token_budget": max_tokens,
        "tokens_used": 0,
        "deadline_ts": time.time() + preset.deadline,
        "iteration": 0,
        "gaps": [],
        "visited_urls": set(),
        "candidate_urls": [],
        "facts": [],
        "citations": [],
        "answer_draft": None,
        "beast_mode": False,
        "stall_counter": 0,
        "trace": [],
    }
