# Research Agent Endpoint for Atomic-Scraper-Service

## Context

The repo `Atomic-Scraper-Service` already exposes atomic scraping primitives (site enrichment, Yandex Maps extraction, Google-search→SERP transformation, interactive sessions). The user has studied two reference research agents — **Jina DeepResearch** (gap-driven ReAct loop, beast-mode fallback, query rewriting) and **Vane** (classification → mode-driven iteration: Speed/Balanced/Quality, tool gating) — documented in [docs/](docs/) together with their own critical analysis ([docs/own_opinion.md](docs/own_opinion.md)).

The goal is to contribute a **research agent** built with **LangGraph + LangChain + a local LM Studio LLM**, exposed as an additional HTTP endpoint on this service. The agent must reuse the service's existing scraping capabilities as its tools — no third-party search API is added; web search is performed by the service itself (Google SERP scraping via the existing stateless router).

Outcome: a `/api/v1/research` endpoint that accepts a natural-language query and returns a markdown report with structured citations + facts. Quality runs may take minutes, so execution goes through the existing Taskiq worker and the endpoint returns a task id for polling.

## Design summary

- **Orchestrator**: LangGraph `StateGraph` — explicit nodes, conditional edges, terminating on budget/iteration/answer.
- **Tools**: LangChain `@tool` wrappers around **the service's own actions** — `web_search` calls the existing Google-SERP scrape path; `scrape_url` wraps `SiteEnrichAction`; `extract_facts` calls the existing `LLMFacade`.
- **LLM**: LM Studio via `langchain_openai.ChatOpenAI(base_url, api_key="lm-studio", model=...)`. Settings via `pydantic-settings`.
- **Execution**: `POST /research/run` enqueues a Taskiq task on the existing Redis broker, returns `{task_id}`. `GET /research/status/{task_id}` polls. Optional `GET /research/stream/{task_id}` SSE for node-event tracing.
- **Modes** (Vane-style): `speed` / `balanced` / `quality` parameterize iterations, search breadth, scrape concurrency, and parallel sub-agents.
- **Loop safety** (Jina-style): token budget + iteration cap + wall-clock deadline + "no-new-URL" stall detector → forces beast-mode answer.

## Graph topology

State (`src/actions/research/state.py`):
```python
class ResearchState(TypedDict):
    query: str
    mode: Literal["speed","balanced","quality"]
    iteration: int
    max_iters: int
    token_budget: int
    tokens_used: int
    deadline_ts: float
    gaps: list[str]
    visited_urls: set[str]
    candidate_urls: list[ScoredUrl]
    facts: list[Fact]
    evidence: list[Citation]
    answer_draft: str | None
    beast_mode: bool
    stall_counter: int
    trace: list[NodeEvent]
```

Nodes (`src/actions/research/nodes.py`, all `async`):
- `classify_node` — LLM → query type (factoid / comparative / exploratory / decomposable); seeds initial `gaps`.
- `plan_node` — gap generator (Jina). Emits 1–N open questions from current evidence.
- `search_node` — calls `web_search` tool over gaps; appends candidate URLs (gated off if `stall_counter >= 2`).
- `rank_dedupe_node` — drops `visited_urls`, scores by domain diversity + simple query-term overlap, keeps top-K per mode. Increments `stall_counter` if zero new URLs.
- `scrape_node` — `asyncio.gather` over `scrape_url` tool with mode-specific concurrency; marks visited.
- `extract_facts_node` — per-doc LLM JSON extraction → `Fact(claim, source_url, snippet, confidence)`.
- `reflect_node` — evaluator (completeness / contradiction / source-quality / freshness / budget). Triggers `beast_mode=True` if `tokens_used >= 0.85*token_budget` OR `time>deadline` OR `stall_counter>=2`.
- `answer_node` — synthesizes markdown answer with inline `[n]` citations from `facts`.
- `writer_node` — assembles final `ResearchReport`.

Edges (`src/actions/research/graph.py`):
```
START → classify → plan → search → rank_dedupe → scrape → extract_facts → reflect
reflect ─cond→ plan        (gaps remain AND iteration<max_iters AND not beast_mode)
reflect ─cond→ answer      (otherwise)
answer  → writer → END
```

## Mode policy (`src/actions/research/modes.py`)

| Mode | max_iters | search_k | scrape_concurrency | scrape_strategy | parallel sub-agents | token_budget | deadline |
|---|---|---|---|---|---|---|---|
| speed | 2 | 3 | 2 | text-only enrich | off | 30k | 120s |
| balanced | 6 | 5 | 3 | full enrich + cleaner | off | 100k | 300s |
| quality | 25 | 8 | 5 | full enrich + retry | on if `classify=decomposable` | ~1M (composite) | 1200s |

**Notes on the budgets:**
- The local Qwen model on the user's machine has a ~100k context window — that is the cap *per LLM call*, not for the whole run. `balanced` is sized to keep most prompts inside one context.
- `quality` budget is **composite across many independent calls** (sub-agents, per-doc fact extraction, repeated reflect/plan steps), so the total token spend across the run can reach ~1M without any single prompt exceeding the model's context window.
- **Deadline semantics: soft checkpoint, not a kill.** When `time > deadline_ts`, `reflect_node` sets `beast_mode=True`, which routes the graph straight to `answer_node` → `writer_node`. The task is **never aborted mid-flight**; it always returns a final `ResearchReport`. Same semantics for the token budget at 85%.

## File layout

```
src/actions/research/
  __init__.py        # imports tasks.py to register Taskiq task
  graph.py           # build_graph(mode) -> CompiledGraph
  nodes.py           # async node fns
  tools.py           # @tool web_search / scrape_url / extract_facts
  state.py           # ResearchState TypedDict + dataclasses
  prompts.py         # per-node system prompts (incl. cognitive personas for query rewriting)
  modes.py           # ResearchMode presets
  tasks.py           # @broker.task run_research_task(request) -> stores report in Redis
src/api/routers/research.py     # POST /run, GET /status/{id}, GET /stream/{id}
src/domain/models/research.py   # ResearchRequest, ResearchReport, Citation, Fact, ResearchStats
```

## Tool layer — reusing the repo's own systems

All tools live in `src/actions/research/tools.py` as `langchain_core.tools.tool` async functions. **No external search API is added.**

- `web_search(query, k)` → invokes the existing stateless scrape path that already handles `google.com/search?q=` (per [AGENTS.md](AGENTS.md) the stateless router supports Google search transformation). Returns `list[SearchHit(url, title, snippet)]`. Concretely: instantiate the same scrape action used by `src/api/routers/stateless.py` and parse SERP results. If a SERP parser doesn't yet exist for this purpose, add a thin `SerpExtractor` next to the existing `SiteEnrichAction` — the scrape itself is already there.
- `scrape_url(url)` → directly awaits `SiteEnrichAction.execute(...)` from [src/actions/site_enricher.py](src/actions/site_enricher.py), reusing the singleton `BrowserPoolManager` from [src/infrastructure/browser/pool_manager.py](src/infrastructure/browser/pool_manager.py).
- `extract_facts(doc, focus)` → uses the existing `LLMFacade.extract` ([src/infrastructure/external_api/facade.py](src/infrastructure/external_api/facade.py)) with the **extraction** LLM (cheaper/local), not the agent LLM.
- (Optional) `yandex_maps_query(...)` → wraps the existing Yandex action for local-business queries; only bound when `classify_node` detects a place/geo intent.

## LLM wiring

Add to [src/core/config.py](src/core/config.py) `Settings`:
```python
RESEARCH_API_BASE: str = "http://localhost:1234/v1"
RESEARCH_API_KEY: str  = "lm-studio"
RESEARCH_MODEL_NAME: str = "qwen/qwen3-4b-2507"   # any LM Studio model with tool-calling
RESEARCH_TEMPERATURE: float = 0.2
RESEARCH_DEFAULT_MODE: str = "balanced"
```
In `graph.py`:
```python
llm = ChatOpenAI(base_url=settings.RESEARCH_API_BASE,
                 api_key=settings.RESEARCH_API_KEY,
                 model=settings.RESEARCH_MODEL_NAME,
                 temperature=settings.RESEARCH_TEMPERATURE)
llm_with_tools = llm.bind_tools([web_search, scrape_url, extract_facts])
```
`extract_facts_node` keeps using the local `LLMFacade` (cheaper extraction model) for per-document parsing.

## Execution model — Taskiq job

- `POST /api/v1/research/run`
  - body: `ResearchRequest(query, mode="balanced", max_tokens?, max_iters?)`
  - enqueues `run_research_task.kiq(request_dict)` on the existing Redis broker ([src/infrastructure/queue/broker.py](src/infrastructure/queue/broker.py)).
  - returns `202 {task_id, status_url}`.
- `GET /api/v1/research/status/{task_id}`
  - reads Redis key `research:{task_id}` → `{phase, iteration, tokens_used, report?}`.
  - returns `running` payload or final `ResearchReport`.
- `GET /api/v1/research/stream/{task_id}` (SSE, optional v2)
  - subscribes to Redis pubsub `research:{task_id}:events`; node events pushed from each node's tail.

The Taskiq task body: build mode → compile graph → `await graph.ainvoke(initial_state)` → persist `ResearchReport` JSON to Redis with TTL (e.g. 24h).

Both routes go behind the existing `verify_api_key` dependency ([src/api/auth.py](src/api/auth.py)) and the rate-limit middleware.

## Output model — `src/domain/models/research.py`

```python
class Citation(BaseModel):
    url: HttpUrl
    title: str
    snippet: str

class Fact(BaseModel):
    claim: str
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)

class ResearchStats(BaseModel):
    iterations: int
    tokens_used: int
    urls_visited: int
    mode: str
    beast_mode_triggered: bool
    elapsed_s: float

class ResearchReport(BaseModel):
    query: str
    mode: str
    answer_markdown: str
    citations: list[Citation]
    facts: list[Fact]
    stats: ResearchStats

class ResearchRequest(BaseModel):
    query: str
    mode: Literal["speed","balanced","quality"] = "balanced"
    max_tokens: int | None = None
    max_iters: int | None = None
```

## Dependencies to add

```
uv add langgraph langchain-core langchain-openai
```
- Skip the umbrella `langchain` package — pulls heavy extras unused here.
- Pin `langchain-core>=0.3` for native Pydantic-v2 (matches our `ConfigDict` models).
- LM Studio works as-is via `ChatOpenAI` — no extra client needed.

## Critical files to modify / reference

- [src/api/main.py](src/api/main.py) — register `research.router`.
- [src/core/config.py](src/core/config.py) — add `RESEARCH_*` settings.
- [src/actions/site_enricher.py](src/actions/site_enricher.py) — reused by `scrape_url` tool.
- [src/infrastructure/external_api/facade.py](src/infrastructure/external_api/facade.py) — reused for `extract_facts`.
- [src/infrastructure/external_api/clients/openai_client.py](src/infrastructure/external_api/clients/openai_client.py) — reference for LM Studio compatibility.
- [src/infrastructure/queue/broker.py](src/infrastructure/queue/broker.py) — Taskiq broker for `run_research_task`.
- [src/infrastructure/browser/pool_manager.py](src/infrastructure/browser/pool_manager.py) — singleton browser pool, shared by scrape tool.
- [src/api/routers/stateless.py](src/api/routers/stateless.py) — reference for SERP scraping path used by `web_search` tool.
- [src/domain/models/requests.py](src/domain/models/requests.py) — pattern reference for `ResearchRequest`.

## Verification plan

**Unit** (`tests/unit/research/`)
- `test_modes.py` — preset values, mode → state initialization.
- `test_nodes_*.py` — each node with `AsyncMock` LLM + stub tool results; assert state mutations (gaps shrink, visited grows, beast-mode trips at 85% budget, stall counter increments on zero-new-URL).
- `test_state_transitions.py` — `should_continue` router truth table.

**Contract** (`tests/contract/test_research_endpoint.py`)
- In-process `ASGITransport`, mock `run_research_task.kiq` and Redis `get/set`.
- `POST /run` → 202 + task_id; `GET /status` → running then final report.
- 401 without API key; 422 on bad mode.

**Integration** (`tests/integration/test_research_graph.py`)
- Compile graph with a `FakeChatModel` returning scripted tool-call sequences and a stub `SearchClient` + stub `SiteEnrichAction`.
- Assert the loop terminates within max_iters and emits a valid `ResearchReport` with ≥1 citation.
- Force beast-mode by setting tiny `token_budget`; assert answer still produced.

**E2E (manual)**
1. `docker compose up` (api + worker + redis).
2. Start LM Studio locally, load a tool-capable model (e.g. Qwen 3 4B).
3. `curl -X POST :8000/api/v1/research/run -H 'X-API-Key: default_internal_key' -d '{"query":"...","mode":"speed"}'`.
4. Poll `/status/{task_id}` until report; assert markdown + citations + facts present.
5. Repeat with `mode=quality` for a decomposable query; confirm parallel sub-agent path and beast-mode bookkeeping in `stats`.

**Lint/type**
- `uv run ruff check src tests`
- `uv run mypy src`

## Risks / tradeoffs

1. **LM Studio context window** — Quality mode (25 iters, multi-doc) can blow 8k–32k contexts; per-node truncation + map-reduce in `extract_facts_node`, never feed full corpus to one prompt.
2. **Tool-calling reliability on small local models** — Qwen-3-4B class models sometimes emit malformed tool JSON; wrap `llm.bind_tools` with one structured-output repair pass before falling back to text parsing.
3. **In-process graph cost** — routing through the existing Taskiq worker (not the API process) keeps API replicas snappy.
4. **Loop runaway** — mode `max_iters` alone is insufficient; the deadline + token budget + stall detector are all required exit conditions.
5. **LangChain import surface** — keep to `langgraph` + `langchain-core` + `langchain-openai`; don't pull umbrella `langchain`.
6. **SERP parsing fragility** — the `web_search` tool depends on Google SERP scraping holding up; isolate the SERP parser so it can be swapped for an alternative (Bing/Yandex via the same stateless scraper) without touching the graph.