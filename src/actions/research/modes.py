"""Research mode presets and state initialization."""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModePreset:
    """Preset configuration for a research mode."""

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
        token_budget=30_000,
        deadline=120.0,
        scrape_strategy="text-only enrich",
    ),
    "balanced": ModePreset(
        max_iters=6,
        search_k=5,
        scrape_concurrency=3,
        token_budget=100_000,
        deadline=300.0,
        scrape_strategy="full enrich + cleaner",
    ),
    "quality": ModePreset(
        max_iters=25,
        search_k=8,
        scrape_concurrency=5,
        token_budget=1_000_000,
        deadline=1200.0,
        scrape_strategy="full enrich + retry",
    ),
}


# Override bounds widened to bracket every preset. Previously [1,20]/[1000,32000]
# was incoherent with `quality` preset (25 iters / 1M tokens).
ITER_OVERRIDE_MIN = 1
ITER_OVERRIDE_MAX = 50
TOKEN_OVERRIDE_MIN = 1_000
TOKEN_OVERRIDE_MAX = 2_000_000


def get_mode_preset(mode: str) -> ModePreset:
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
    """Materialise initial LangGraph state from a preset + optional overrides."""
    max_iters = max_iters_override if max_iters_override is not None else preset.max_iters
    max_tokens = max_tokens_override if max_tokens_override is not None else preset.token_budget

    if max_iters_override is not None and not (
        ITER_OVERRIDE_MIN <= max_iters_override <= ITER_OVERRIDE_MAX
    ):
        raise ValueError(
            f"max_iters override must be in [{ITER_OVERRIDE_MIN}, {ITER_OVERRIDE_MAX}]"
        )
    if max_tokens_override is not None and not (
        TOKEN_OVERRIDE_MIN <= max_tokens_override <= TOKEN_OVERRIDE_MAX
    ):
        raise ValueError(
            f"max_tokens override must be in [{TOKEN_OVERRIDE_MIN}, {TOKEN_OVERRIDE_MAX}]"
        )

    now = time.time()
    return {
        "query": query,
        "mode": mode_str,
        "max_iters": max_iters,
        "max_tokens": max_tokens,
        "token_budget": max_tokens,
        "tokens_used": 0,
        "started_ts": now,
        "deadline_ts": now + preset.deadline,
        "iteration": 0,
        "gaps": [],
        "visited_urls": [],
        "candidate_urls": [],
        "current_batch": [],
        "scraped_content": [],
        "facts": [],
        "citations": [],
        "answer_draft": None,
        "final_answer": None,
        "final_report": None,
        "beast_mode": False,
        "stall_counter": 0,
        "trace": [],
    }
