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
- **Inactivity Monitoring**: A background cleanup worker monitors `last_active` timestamps and terminates idle sessions after 10 minutes.
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
- Python 3.12 + FastAPI, Taskiq, Playwright, Redis, Pydantic v2, LangGraph, LangChain (011-auto-research-agent)
- Redis (task queues), in-memory with 24-hour retention (per spec) (011-auto-research-agent)
- Python 3.12 + FastAPI, Playwright, Taskiq, Redis, Pydantic v2, httpx, LangGraph, LangChain (013-fix-impl)
- Redis (task queues), in-memory task store (24h retention) (013-fix-impl)

- Python 3.12, FastAPI, Taskiq (Redis broker), Playwright, Redis, Pydantic v2, OpenAI-compatible API, HTTPX
- `uv` for dependency management and running scripts

## Project Structure

```text
src/
├── api/
│   ├── routers/           # stateless.py, sessions.py, health.py, yandex_maps.py, enrichment.py
│   ├── middleware/        # rate_limit.py (per-domain token bucket), auth.py (X-API-Key)
│   └── main.py
├── domain/
│   ├── models/            # requests.py, dsl.py, business_card.py, enriched_content.py
│   ├── utils/             # content_cleaner.py
│   └── registry/          # action_registry.py
├── infrastructure/
│   ├── browser/           # pool_manager.py, stealth_pool.py, user_agent_pool.py, proxy_provider.py
│   ├── rate_limiter/      # token_bucket.py
│   └── external_api/      # facade.py, clients/
├── actions/
│   ├── research/          # nodes.py, tools.py, modes.py, state.py, graph.py (LangGraph agent)
│   ├── navigation.py, interaction.py, extraction.py, yandex_maps.py, site_enricher.py
└── core/                  # config.py, logging.py
tests/
├── unit/
├── contract/
├── integration/
└── e2e/
```

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
| `POST /api/v1/yandex-maps/extract` | Yes | Extract business data from Yandex Maps |
| `POST /api/v1/enrich` | Yes | Extract clean text from company websites |
| `POST /api/v1/research/run` | Yes | Start research task (LangGraph agent) |
| `GET /api/v1/research/status/{task_id}` | Yes | Get research task status |
| `GET /api/v1/research/stream/{task_id}` | Yes | Stream research progress (SSE) |
| `POST /sessions` | Yes | Create browser session |
| `POST /sessions/{id}/command` | Yes | Execute DSL command |
| `DELETE /sessions/{id}` | Yes | Delete browser session |
| `WS /ws/{session_id}` | — | WebSocket for interactive sessions |

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
- 013-fix-impl: Added Python 3.12 + FastAPI, Playwright, Taskiq, Redis, Pydantic v2, httpx, LangGraph, LangChain
- 011-auto-research-agent: Added Python 3.12 + FastAPI, Taskiq, Playwright, Redis, Pydantic v2, LangGraph, LangChain

### 2026-05-07
- Fixed `Dockerfile`: `playwright install` → `uv run playwright install --with-deps chromium`

### 2026-05-01

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
