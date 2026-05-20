"""LangGraph state definitions for the Research Agent."""

from typing import TypedDict, Literal, Optional


class ScoredUrl(TypedDict, total=False):
    """A URL produced by web_search with optional rank score."""

    url: str
    title: str
    snippet: str
    score: float


class NodeEvent(TypedDict):
    """Event emitted during graph execution (logging/SSE hook)."""

    type: Literal["node_entered", "node_exited", "progress", "completed"]
    node: Optional[str]
    timestamp: str
    elapsed_ms: Optional[int]
    data: dict


class ResearchState(TypedDict, total=False):
    """State maintained throughout LangGraph research execution.

    `total=False` so node return dicts only need to set the keys they actually
    change — LangGraph default reducer merges them into the running state.
    """

    query: str
    mode: str
    query_type: str
    max_iters: int
    max_tokens: int
    token_budget: int
    tokens_used: int
    started_ts: float
    deadline_ts: float
    iteration: int
    gaps: list[str]
    visited_urls: list[str]
    candidate_urls: list[ScoredUrl]
    current_batch: list[ScoredUrl]
    scraped_content: list[dict]
    facts: list[dict]
    citations: list[dict]
    answer_draft: Optional[str]
    final_answer: Optional[str]
    final_report: Optional[dict]
    beast_mode: bool
    stall_counter: int
    trace: list[NodeEvent]


def create_initial_state(
    query: str,
    mode: str,
    max_iters_override: Optional[int] = None,
    max_tokens_override: Optional[int] = None,
) -> ResearchState:
    """Build the initial ResearchState dict for a fresh task."""
    from src.actions.research.modes import get_mode_preset, mode_to_initial_state

    preset = get_mode_preset(mode)
    return mode_to_initial_state(
        query, mode, preset, max_iters_override, max_tokens_override
    )
