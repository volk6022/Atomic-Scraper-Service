# Agent Coordination: Atomic Scraper Service

This document defines the agentic roles and coordination strategies for the Smart Scraping LLM API project.

## Agent Personas

### 1. Scraper Orchestrator (Stateless)
- **Responsibility**: Manages high-throughput atomic scraping tasks.
- **Capabilities**: Selects optimal proxies, handles retries, and transforms results into Serper-compatible formats.
- **Integration**: Uses `ScrapeClient` and `SearchClient`.

### 2. Browser Session Actor (Stateful)
- **Responsibility**: Executes interactive DSL commands within isolated browser contexts.
- **Capabilities**: Navigation (goto, scroll), Interaction (click, fill), and Extraction (screenshot, DOM).
- **Coordination**: Communicates via Redis Pub/Sub channels (`cmd:{id}`, `res:{id}`).

### 3. AI Grounding Specialist
- **Responsibility**: Interprets UI elements and provides grounding for autonomous interactions.
- **Capabilities**: Utilizes Omni-Parser for coordinate-based click prediction and Jina for structured data extraction.
- **Provider**: Integrated via `LLMFacade` and specialized infrastructure clients.

## Coordination Protocol

- **State Transitions**: Sessions transition from `STARTING` to `ACTIVE` upon WebSocket connection.
- **Inactivity Monitoring**: A background cleanup worker monitors `last_active` timestamps. `SESSION_INACTIVITY_TIMEOUT` is currently set to **1800 s** in `docker-compose.override.yml` (spec 009 FR-007 / constitution III still call for 600 s — known drift, see `docs/codebase-report/20-spec-vs-reality.md` C-03).
- **Command Loop**:
    1. Client sends DSL Command via WebSocket.
    2. API Gateway publishes command to Redis.
    3. Session Actor (Taskiq) consumes command, executes in Playwright, and publishes result back to Redis.
    4. API Gateway forwards result to Client.

## Resource Lifecycle
- **Global Pool**: A shared `Browser` instance is reused to minimize startup latency.
- **Isolated Contexts**: Each session (stateless or stateful) gets a unique `BrowserContext` for data isolation.
- **Cleanup**: Automatic disposal of contexts on task completion or timeout.

---

# Atomic-Scraper-Service Development Guidelines

Last updated: 2026-05-12

## Active Technologies
- Python 3.12, FastAPI, Taskiq (Redis broker), Playwright, Redis, Pydantic v2, httpx, OpenAI-compatible API, PyYAML
- `uv` for dependency management and running scripts
- Research agent: flat tool-calling loop (`openai.AsyncOpenAI.chat.completions` with `tool_choice="auto"`), no LangGraph
- LangGraph / LangChain dependencies remain in `pyproject.toml` for now but are unused by the research subsystem
- Redis (task queue + KV) with 24h retention; mapped to host port **16379** by docker-compose to keep the dev port from clashing with other local Redis instances

## Project Structure

```text
src/
├── api/
│   ├── routers/           # health.py, stateless.py, sessions.py, yandex_maps.py, enrichment.py, research.py
│   ├── middleware/        # __init__.py, rate_limit.py (per-domain token bucket on Host header)
│   ├── websockets/        # handler.py, manager.py (no auth on /ws/{session_id})
│   ├── auth.py            # X-API-Key dependency (NOTE: lives directly in src/api/, not src/api/middleware/)
│   └── main.py
├── domain/
│   ├── models/            # requests.py, dsl.py, enriched_content.py, errors.py,
│   │                      # research.py, rate_limit_rule.py, yandex_organization.py, yandex_review.py
│   ├── utils/             # content_cleaner.py
│   └── registry/          # action_registry.py
├── infrastructure/
│   ├── browser/           # pool_manager.py, stealth_pool.py, user_agent_pool.py, proxy_provider.py, session_manager.py
│   ├── rate_limiter/      # token_bucket.py
│   ├── external_api/      # facade.py, searxng_client.py, clients/openai_client.py
│   ├── queue/             # broker.py, session_actor.py, cleanup_worker.py, workers.py, research_task.py
│   └── tasks/             # research_store.py
├── actions/
│   ├── research/          # agent.py (run_research, flat loop), tools.py, modes.py,
│   │                      # research_agent_prompts.yaml (all prompts), llm_utils.py
│   ├── __init__.py        # side-effect imports of submodules to trigger registry decorators
│   ├── navigation.py, interaction.py, extraction.py, yandex_maps.py, site_enricher.py
├── core/                  # config.py (pydantic-settings), logging.py (stdlib)
└── mcp_server.py          # FastMCP stdio server exposing REST endpoints as MCP tools
tests/
├── unit/                  # ~76 functions in 10 files (30 in research/)
├── contract/              # 10 files, ~14 endpoints via ASGITransport
├── integration/           # 11 files; structural + in-process FastAPI + fake-Playwright
└── e2e/                   # 5 files / 23 tests; only 2 hit live localhost:8000
```

NOTE: `src/actions/base.py` and `src/actions/ai_actions.py` are referenced in older `STRUCTURE.md` but do **not** exist — DSL actions are bare async functions, not classes (see `docs/codebase-report/07-actions-basic.md`). Likewise `jina_client.py`, `omni_client.py`, `business_card.py` referenced in legacy docs are absent.

## Commands

```bash
# Install dependencies
uv sync

# Install Playwright browsers (MUST use uv run — playwright lives in .venv)
uv run playwright install --with-deps chromium

# Run all tests (99 tests, no Docker required)
python -m pytest tests/ -q

# Run live E2E tests (require docker compose up)
python -m pytest tests/e2e/test_site_enrichment_flow.py::test_enrichment_returns_clean_text \
                 tests/e2e/test_yandex_maps_full_flow.py::test_yandex_maps_endpoint_returns_businesses -v

# Docker
docker compose up -d
docker compose logs api --tail=30

# Lint / type-check
uv run ruff check src tests
uv run mypy src
```

## Code Style

- Python 3.12 standard conventions; async-first (all browser/HTTP I/O is `async`/`await`)
- No docstrings on trivial helpers; only add comments for non-obvious invariants
- New actions must be registered in `src/actions/__init__.py` and `src/domain/models/dsl.py`

## API Authentication

All protected endpoints require `X-API-Key: <API_KEY>` header. Default value: `default_internal_key` (set in `.env` and `src/core/config.py`). Tests use this same value.

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /healthz` | No | Health check (Redis + browser pool status) |
| `POST /scraper` | Yes | Atomic Playwright scrape via shared pool |
| `POST /serper` | Yes | Serper-compatible search (backed by **SearXNG**, not Playwright→Google) |
| `POST /omni-parse` | Yes | OmniParser UI grounding via LLMFacade |
| `POST /html-to-md` | Yes | HTML → Markdown conversion (replaces legacy `/jina-extract`) |
| `POST /api/v1/yandex-maps/extract` | Yes | Extract organizations from Yandex Maps |
| `POST /api/v1/yandex-maps/reviews` | Yes | Fetch reviews for a Yandex business OID |
| `POST /api/v1/enrich` | Yes | Extract clean text from company websites |
| `POST /api/v1/research/run` | Yes | Start research task (flat-loop agent), returns 202; body supports `query`, `mode`, `language`, optional `output_schema`, `max_iters`, `max_tokens` |
| `GET /api/v1/research/status/{task_id}` | Yes | Get research task status |
| `GET /api/v1/research/stream/{task_id}` | Yes | SSE stream of research progress (`POLL_INTERVAL=2s`, `SSE_TIMEOUT=1800s`) |
| `POST /sessions` | Yes | Create browser session (enqueues `run_session_actor.kiq`) |
| `POST /sessions/{id}/command` | Yes | Publish DSL command on Redis `cmd:{id}`, wait ≤60 s on `res:{id}` |
| `DELETE /sessions/{id}` | Yes | Delete browser session |
| `WS /ws/{session_id}` | **none** | WebSocket bridge to Redis pub/sub — **no auth, no JSON validation** (see report 02 / C-06) |

Notes: auth dependency raises `HTTP 403` (spec 011 expects 401 — drift C-07). Source: `docs/codebase-report/01-api-routers.md`.

## Proxy Configuration

`proxies.txt` in the project root — one proxy per line, format: `http://user:pass@host:port`

- Loaded at startup by `ProxyProvider` (`src/infrastructure/browser/proxy_provider.py`)
- Rotated randomly per Yandex Maps request
- Mounted into Docker containers as a read-only bind mount
- **IMPORTANT**: create the file before first `docker compose up`. If Docker creates it as a directory (Windows Docker Desktop quirk), run `docker compose down && docker compose up -d`
- **Yandex Maps requires residential proxies**. Datacenter IPs (e.g. Webshare) work for curl but Chromium gets blocked at the TLS/browser level

## Key Implementation Notes

### Playwright in Docker
Playwright is installed via `uv run playwright install --with-deps chromium` in the Dockerfile — **not** bare `playwright install`. `uv sync` installs into `.venv` which is not on `$PATH`.

### Proxy wiring
- `ProxyProvider.get_proxy()` returns a proxy URL string or `{}` (empty dict, falsy) when no proxies are configured
- `ProxyProvider._load_proxies()` uses `is_file()` not `exists()` — guards against Docker creating a directory stub at the mount path
- `BrowserPoolManager.create_context(stealth=True, proxy=url)` passes proxy as `{"server": url}` to `browser.new_context()` — Playwright does not support setting proxy after context creation

### Action Registry
Register new actions in two places:
1. `src/domain/models/dsl.py` — add `CommandType` enum value
2. `src/actions/<module>.py` — call `action_registry.register(CommandType.X)(MyAction)` at module level
3. `src/actions/__init__.py` — import the module so registration runs at startup

### Rate Limiting
- Middleware in `src/api/middleware/rate_limit.py` intercepts all requests except `/healthz`, `/docs`, `/openapi.json`
- Redis required for limiting to work; if Redis is unreachable, requests are allowed through with a warning log
- In Docker: the API container must use the `redis` service hostname (not `localhost`) — set `REDIS_URL=redis://redis:6379` in `.env` for containerized deployments

### GeoCenter Validation
`YandexMapsExtractRequest` uses a nested `GeoCenter` model with `lat ∈ [-90, 90]` and `lng ∈ [-180, 180]`. Invalid coordinates return `422`. The router converts `GeoCenter` to `dict` before passing to the action.

## Test Suite Status (2026-05-07)

**99 passed, 0 failed, 0 skipped**

| Suite | Count | Notes |
|-------|-------|-------|
| unit/ | 17 | Fully mocked |
| contract/ | 28 | In-process FastAPI, mocked actions |
| integration/ | 31 | Mocked browser; Docker config file checks |
| e2e/ | 23 | 21 in-process, 2 hit live localhost:8000 |

The 2 live E2E tests (`test_enrichment_returns_clean_text`, `test_yandex_maps_endpoint_returns_businesses`) require `docker compose up`. The Yandex Maps test validates the API stack and response schema — actual businesses require residential proxies.

## Recent Changes

### 2026-05-29 — Research Agent rewrite
- Replaced the 9-node LangGraph research agent (`graph.py`/`nodes.py`/`state.py`,
  removed) with a flat tool-calling loop in `src/actions/research/agent.py:run_research`.
- Two output modes: free-form markdown (`submit_answer`) or caller-supplied JSON
  Schema (`submit_result`). Critic-gate on submit (`RESEARCH_CRITIC_PASS_SCORE`,
  default 8.5), force-accept after `RESEARCH_MAX_SUBMIT_REJECTS` (default 2).
- All numeric knobs moved into `Settings.RESEARCH_*` (env-overridable); all prompts
  into `src/actions/research/research_agent_prompts.yaml`.
- `ResearchReport` redesigned: `answer_markdown`, `structured_output`, `sources`,
  `critic`, expanded `ResearchStats`. `Citation`/`Fact` removed.
- `tools.py` stripped of `@tool` decorator + `extract_facts*` helpers.
- `OpenAICompatibleClient` gained multi-turn `chat()` method.
- Docker-compose Redis now maps **host port 16379** to match `.env`.

### 2026-05-07
- Fixed `Dockerfile`: `playwright install` → `uv run playwright install --with-deps chromium`

### 2026-05-01

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
