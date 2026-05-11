"""LangGraph state definitions for Research Agent"""

from typing import TypedDict, Literal, Optional
import time


class ScoredUrl(TypedDict):
    """A URL with relevance score from search"""

    url: str
    title: str
    score: float


class NodeEvent(TypedDict):
    """Event emitted during graph execution"""

    type: Literal["node_entered", "node_exited", "progress", "completed"]
    node: Optional[str]
    timestamp: str
    elapsed_ms: Optional[int]
    data: dict


class ResearchState(TypedDict):
    """State maintained throughout LangGraph research execution"""

    query: str
    mode: str
    max_iters: int
    token_budget: int
    tokens_used: int
    deadline_ts: float
    iteration: int
    gaps: list[str]
    visited_urls: set[str]
    candidate_urls: list[ScoredUrl]
    facts: list[dict]
    citations: list[dict]
    answer_draft: Optional[str]
    beast_mode: bool
    stall_counter: int
    trace: list[NodeEvent]


def create_initial_state(
    query: str,
    mode: str,
    max_iters_override: Optional[int] = None,
    max_tokens_override: Optional[int] = None,
) -> ResearchState:
    """Create initial state for a research task"""
    from src.actions.research.modes import get_mode_preset, mode_to_initial_state

    preset = get_mode_preset(mode)
    return mode_to_initial_state(
        query, mode, preset, max_iters_override, max_tokens_override
    )
