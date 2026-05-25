# Web Interactions: Atomic Scraper Service

This document describes the available interaction methods, their JSON models, and intended usage.
It reflects the **actual implementation** in `src/api/` and `src/actions/` as cross-referenced in
`docs/codebase-report/` (reports 01, 02, 07, 13, 19).

All protected endpoints require the `X-API-Key` header. An invalid key currently returns **403**
(spec 011 expects 401 — see report 20, C-07). Rate-limit middleware is global but keys on the
incoming `Host` header (report 20, C-01).

## 1. Stateless REST API

Fast, atomic operations that do not require a persistent browser session.

### `POST /scraper`
Scrapes the full HTML content of a URL via the shared Playwright pool (`pool_manager`).
- **Request** — `ScrapeRequest`
```json
{
  "url": "https://example.com",
  "proxy": "http://user:pass@host:port",
  "wait_until": "domcontentloaded"
}
```
- **Response** — `ScrapeResponse`
```json
{
  "id": "uuid-v4",
  "url": "https://example.com",
  "content": "<html>...</html>",
  "status": "success",
  "error": null
}
```
Note: errors are returned inside a 200 OK with `status: "failed"` rather than as a 4xx/5xx.

### `POST /serper`
Google-compatible search response shape, **backed by SearXNG** (`search_client` singleton, not
Playwright → google.com). Spec 013 FR-001/FR-002 referenced Playwright; the implementation
switched to SearXNG (report 20, C-04).
- **Request** — `SearchRequest`
```json
{
  "q": "best coffee in NYC",
  "num": 10
}
```
- **Response** — `SearchResponse`
```json
{
  "searchParameters": { "q": "...", "type": "search", "engine": "google" },
  "organic": [
    { "title": "Example", "link": "https://example.com", "snippet": "...", "position": 1 }
  ]
}
```

### `POST /omni-parse`
Runs an OmniParser/UI-grounding LLM call via the orchestration `LLMFacade`.
- **Request** — `OmniParseRequest`
```json
{
  "base64_image": "<png-base64>",
  "prompt": "Identify the primary call-to-action button"
}
```
- **Response**: untyped `dict` (no `response_model` declared).

### `POST /html-to-md`
Local HTML → Markdown conversion using `content_cleaner` (replaces the spec'd `/jina-extract`,
which is no longer mounted — report 20, C-05).
- **Request** — `HtmlToMdRequest`
```json
{
  "html": "<html>...</html>"
}
```
- **Response**: untyped `dict` containing the markdown payload.

### `POST /api/v1/yandex-maps/extract`
Extracts organisations from Yandex Maps via `YandexMapsExtractAction` (Playwright + XHR intercept).
- **Request** — `YandexMapsExtractRequest`
```json
{
  "category": "coffee shop",
  "lat": 59.9343,
  "lng": 30.3351,
  "radius": 1000
}
```
- **Response** — `YandexMapsExtractResponse` (list of `YandexOrganization`, ~65 fields, `extra="allow"`).
- **Errors**: `503` on `YandexCaptchaError`; `500` generic catch-all (no 4xx breakdown).

### `POST /api/v1/yandex-maps/reviews`
Fetches reviews for a Yandex Maps organisation via `YandexMapsReviewsAction`.
- **Request** — `YandexMapsReviewsRequest` (organisation id + paging).
- **Response** — `YandexMapsReviewsResponse` (list of `YandexReview`).

### `POST /api/v1/enrich`
Crawls a company website and returns cleaned text (≤ 600 words per `EnrichedContent` validator).
- **Request** — `EnrichRequest`
```json
{
  "url": "https://acme.example",
  "crawl_about": true,
  "crawl_services": false
}
```
- **Response** — `EnrichResponse` (cleaned text + metadata).
- **Errors**: `500` generic on any exception (spec'd 400/413 are not implemented).

### `GET /healthz`
No auth. Returns Redis ping + browser-pool probe. SLA < 200 ms. Does not currently emit `503` on
component failure (report 20, C-09).

---

## 2. Stateful Interactive Sessions

Long-running browser actors managed via Redis pub/sub. Each session is served by a dedicated
Taskiq actor (`run_session_actor`) holding one Playwright context. Two transports are exposed for
sending DSL commands: a synchronous REST endpoint and a WebSocket bridge.

### `POST /sessions`
Initialises a persistent browser actor. Enqueues `run_session_actor.kiq(...)`.
- **Response**:
```json
{
  "session_id": "uuid-v4",
  "status": "active"
}
```

### `DELETE /sessions/{session_id}`
Terminates a persistent browser actor manually (cleanup via Redis).
- **Response**:
```json
{
  "status": "success",
  "message": "Session uuid-v4 termination signal sent"
}
```

### `POST /sessions/{session_id}/command`
Sends a single DSL command and waits up to **60 s** for the actor's reply.
Internally publishes to Redis `cmd:{session_id}` and blocks on `res:{session_id}`.
Recommended for **MCP / programmatic clients** that cannot hold a persistent WS connection.

- **Request** — `CommandRequest`
```json
{
  "type": "goto",
  "params": { "url": "https://news.ycombinator.com" }
}
```
- **Response**: the action result object, e.g.
```json
{ "status": "success", "message": "Navigated to https://news.ycombinator.com" }
```
- **Errors**:
  - `503 REDIS_UNAVAILABLE` — Redis connection / timeout failure.
  - `504 COMMAND_TIMEOUT` — actor did not respond within 60 s (session may have expired).
  - `422` — malformed request body.

### `WS /ws/{session_id}`
WebSocket bridge between the client and the session actor.

**Important — implementation reality (report 02):**
- **No authentication** on this endpoint (no `Depends(get_api_key)`), and no validation that
  `session_id` belongs to the caller. Anyone who can reach the server and guess a `session_id` can
  read its `res:` stream (report 20, C-06).
- **No payload validation**: the handler does `command = json.loads(data)` and publishes the
  resulting object **as-is** to Redis `cmd:{session_id}`. Neither the spec-declared `{action, params}`
  envelope nor the `{type, params}` envelope is enforced — the actor decides what to do with it.
  In practice you should send the **DSL command shape** (see §3 below), because the registered
  handlers expect that schema.
- **No heartbeat / ping-pong**, no message-size cap, no per-connection rate limit, and the
  background `res:` listener task is not explicitly cancelled on disconnect.
- **No TERMINATE on disconnect**: closing the WebSocket does not stop the underlying actor — the
  session only ends on `DELETE /sessions/{id}` or on inactivity TTL.

Recommended for **interactive / streaming clients** (browser frontends, the `test_ws.py` script,
long-running automation) that need bi-directional, low-latency communication.

---

## 3. Research Agent (Async LangGraph)

Asynchronous auto-research agent built on LangGraph (9 nodes, see report 13). Submission is
fire-and-forget into Taskiq; clients then poll or stream.

### `POST /api/v1/research/run`
Enqueues `execute_research_task.kiq(task_id)`. Returns **202 Accepted**.
- **Request** — `ResearchRequest`
```json
{
  "query": "Compare Taskiq vs Celery for async Python workloads",
  "mode": "balanced",
  "max_iterations": null,
  "max_tokens": null
}
```
- **Response** — `ResearchTaskCreateResponse`
```json
{
  "task_id": "uuid-v4",
  "status": "queued"
}
```
- **Errors**: `429` when `concurrent > MAX_CONCURRENT_RESEARCH_TASKS`.

### `GET /api/v1/research/status/{task_id}`
Polls task state in `research_store` (Redis).
- **Response** — `ResearchTaskStatus`
```json
{
  "task_id": "uuid-v4",
  "status": "running",
  "report": null,
  "error": null
}
```
- **Errors**: `404` if the task is unknown or expired.

### `GET /api/v1/research/stream/{task_id}`
SSE stream of node events from the LangGraph trace. Server polls `research_store` every
`POLL_INTERVAL = 2.0 s`, max stream duration `SSE_TIMEOUT = 1800 s`.

### Modes (report 13, `src/actions/research/modes.py`)

The `mode` field selects a `ModePreset`. Each preset bundles the iteration cap, search breadth,
scrape concurrency, token budget and wall-clock deadline:

| Parameter             | `speed`  | `balanced` | `quality`  |
|-----------------------|---------:|-----------:|-----------:|
| `max_iters`           |        2 |          6 |         25 |
| `search_k`            |        3 |          5 |          8 |
| `scrape_concurrency`  |        2 |          3 |          5 |
| `token_budget`        |   30 000 |    100 000 |  1 000 000 |
| `deadline` (seconds)  |      120 |        300 |      1 200 |
| `scrape_strategy`     | text-only enrich | full enrich + cleaner | full enrich + retry |

Optional overrides: `max_iterations` ∈ [1, 50], `max_tokens` ∈ [1 000, 2 000 000].

### Final report shape — `ResearchReport`

The terminal `writer_node` produces a markdown report with inline numeric citations
plus structured metadata:

```json
{
  "query": "Compare Taskiq vs Celery ...",
  "mode": "balanced",
  "answer_markdown": "Taskiq is an async-first ... [1]. Celery, by contrast, ... [2].",
  "citations": [
    { "n": 1, "url": "https://...", "title": "..." },
    { "n": 2, "url": "https://...", "title": "..." }
  ],
  "facts": [
    { "claim": "...", "source_url": "https://...", "confidence": 0.9 }
  ],
  "stats": {
    "iterations": 4,
    "visited_urls": ["https://...", "..."],
    "elapsed_seconds": 87.3,
    "tokens_used": 0
  }
}
```

Note: `tokens_used` is initialised to 0 but never incremented in current code — the 85%-of-
`token_budget` beast-mode trigger from constitution X(b) is therefore inert (report 20, C-02).
The other three loop-safety constraints (deadline, iteration cap, stall counter) are enforced.

---

## 4. DSL Command Interactions

Commands are sent either over `WS /ws/{session_id}` or via `POST /sessions/{session_id}/command`
in the format:
`{"type": "<command>", "params": { ... }}`

The session actor looks up the handler with `action_registry.get_action(CommandType.<NAME>)`; if
no handler is registered the lookup returns `None` and the command fails inside the actor.

### Registered handlers (report 07)

The handlers below are registered via `@action_registry.register(...)` decorators and imported by
`src/actions/__init__.py`. They are the only DSL commands that actually work.

#### `goto`
Navigates the current session to a new URL.
```json
{
  "type": "goto",
  "params": {
    "url": "https://news.ycombinator.com"
  }
}
```

#### `scroll`
Scrolls the active page.
```json
{
  "type": "scroll",
  "params": {
    "direction": "down",
    "amount": 500
  }
}
```

#### `click_coord`
Performs a mouse click at relative coordinates (0.0 to 1.0). Coordinates are scaled to the
page's `viewport_size` before `page.mouse.click()` is called.
```json
{
  "type": "click_coord",
  "params": {
    "x": 0.5,
    "y": 0.2
  }
}
```

#### `type`
Fills a text input field identified by a CSS selector (`page.fill`).
```json
{
  "type": "type",
  "params": {
    "selector": "input[name='q']",
    "text": "Taskiq automation"
  }
}
```

#### `screenshot`
Captures a base64-encoded PNG of the current viewport. Returns `{"status": "success", "data": "<base64-png>"}`.
There is no explicit size cap; large viewports produce multi-MB Redis pub/sub payloads.
```json
{
  "type": "screenshot",
  "params": {}
}
```

### Declared but not implemented

The following values exist in the `CommandType` enum (`src/domain/models/dsl.py`) and were
historically advertised in this document, but **no handler is registered** for them — neither
`src/actions/ai_actions.py` nor any equivalent module exists. Calls will fail because
`action_registry.get_action(CommandType.CLICK_OMNI)` / `EXTRACT_JINA` returns `None` (report 07).

#### `click_omni` — not implemented
Was intended to click an element by visual description via OmniParser:
```json
{
  "type": "click_omni",
  "params": { "element_description": "The big red 'Login' button" }
}
```

#### `extract_jina` — not implemented
Was intended to extract structured data via Jina Reader LM:
```json
{
  "type": "extract_jina",
  "params": { "extraction_schema": { "title": "string", "price": "number" } }
}
```

Also declared in spec but absent from the enum entirely: `site_enrich`, `apply_stealth` (these are
only reachable via the REST endpoints in §1, not via DSL).

---

## 5. MCP Server

A FastMCP wrapper (`src/mcp_server.py`, stdio transport) re-exports the REST endpoints above as
MCP tools for Claude Desktop / OpenCode. Each tool is a thin `httpx` shim that POSTs/GETs against
the FastAPI app with the `X-API-Key` header. Session DSL tools route through
`POST /sessions/{id}/command` rather than the WebSocket.

See `README.md` (section "MCP Server") and `docs/codebase-report/19-mcp-server.md` for the full
tool catalogue and known issues (hard-coded `BASE_URL` / `API_KEY`, the `jina_extract` and
`session_extract_jina` tools pointing at the removed `/jina-extract` endpoint, etc.).
