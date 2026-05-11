"""LangGraph StateGraph definition for Research Agent"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.actions.research.state import ResearchState
from src.actions.research import nodes


REQUIRED_NODES = [
    "classify",
    "plan",
    "search",
    "rank_dedupe",
    "scrape",
    "extract_facts",
    "reflect",
    "answer",
    "writer",
]


def should_continue(state: ResearchState) -> str:
    """Determine if graph should continue or terminate"""
    if state["beast_mode"]:
        return "answer"

    if state["iteration"] >= state["max_iters"]:
        return "answer"

    if state["stall_counter"] >= 2:
        return "answer"

    if not state["gaps"]:
        return "answer"

    return "plan"


ANSWER_TO_WRITER = "writer"


def build_graph(mode: str) -> StateGraph:
    """Build and compile the research agent graph"""
    graph = StateGraph(ResearchState)

    graph.add_node("classify", nodes.classify_node)
    graph.add_node("plan", nodes.plan_node)
    graph.add_node("search", nodes.search_node)
    graph.add_node("rank_dedupe", nodes.rank_dedupe_node)
    graph.add_node("scrape", nodes.scrape_node)
    graph.add_node("extract_facts", nodes.extract_facts_node)
    graph.add_node("reflect", nodes.reflect_node)
    graph.add_node("answer", nodes.answer_node)
    graph.add_node("writer", nodes.writer_node)

    graph.set_entry_point("classify")

    graph.add_edge("classify", "plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "rank_dedupe")
    graph.add_edge("rank_dedupe", "scrape")
    graph.add_edge("scrape", "extract_facts")
    graph.add_edge("extract_facts", "reflect")

    graph.add_conditional_edges(
        "reflect",
        should_continue,
        {
            "plan": "plan",
            "answer": "answer",
        },
    )

    graph.add_edge("answer", "writer")
    graph.add_edge("writer", END)

    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    return compiled
