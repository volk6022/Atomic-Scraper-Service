# Research Agent: nodes — **REMOVED**

> The LangGraph node set (`classify / plan / search / rank_dedupe / scrape /
> extract_facts / reflect / answer / writer`) was deleted on **2026-05-29**
> together with `src/actions/research/graph.py`, `nodes.py`, and `state.py`.
>
> The replacement is a single flat tool-calling loop in
> `src/actions/research/agent.py:run_research`. See report
> **[13-research-graph-state.md](13-research-graph-state.md)** for the
> current architecture, and report
> **[15-research-tools.md](15-research-tools.md)** for the tool layer.

## Why this file is kept

Earlier reports (05, 11, 20) cross-reference report 14. Rather than
rewrite every back-link this stub stays as a sign-post.

## What used to live here

A nine-node LangGraph topology with conditional routing out of
`reflect_node`. State was a `TypedDict(total=False)` named `ResearchState`
with fields like `gaps`, `candidate_urls`, `visited_urls`, `facts`,
`citations`, `beast_mode`, `stall_counter`. Loop-safety was enforced by
`reflect_node` flipping `beast_mode` on any of: deadline reached, stall
counter ≥ 2, token-budget ≥ 85% (latter was dead code — `tokens_used` never
incremented). The compiled graph was driven by
`infrastructure/queue/research_task.py` via `graph.ainvoke(state, config={"configurable": {"thread_id": task_id}})`.

## Where the equivalent behaviour lives now

| Pre-2026-05-29 (LangGraph node)         | Now (`agent.py`)                                              |
|------------------------------------------|----------------------------------------------------------------|
| `classify_node`, `plan_node`             | implicit — the LLM picks its own next tool inside the flat loop |
| `search_node`                            | `web_serp` tool dispatch                                       |
| `rank_dedupe_node`                       | gone — the LLM does this itself in-context                     |
| `scrape_node`                            | `web_scrape` tool dispatch (sequential, concurrency-1)         |
| `extract_facts_node` (LLM + regex)       | `goal_conditioned_extract` (regex relevance trim) + the model reasoning over the trimmed text |
| `reflect_node` (beast-mode)              | deadline / token-cap guards + critic-gate + force-submit on exit |
| `answer_node`, `writer_node`             | the `submit_answer` / `submit_result` terminal tool call        |
| `should_continue` router (in `graph.py`) | `tool_choice="auto"` — the model itself decides whether to keep calling tools or to submit |

## Removed dependencies

- `langgraph.graph.StateGraph` + `MemorySaver` checkpointer.
- `langchain_core.tools.tool` decorator on the two web tools.
- `tools.extract_facts` (regex fallback) + `tools.extract_facts_llm` (LLM helper) + `EXTRACT_FACTS_SCHEMA`.

`langgraph` / `langchain-core` / `langchain-openai` are still listed in `pyproject.toml` as transitive options, but no research code imports them.
