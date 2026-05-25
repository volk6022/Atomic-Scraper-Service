# Atomic Scraper Service

High-throughput atomic scraping and stateful interactive browser sessions with LLM orchestration.

## Features

- **Stateless Scraper**: Fast atomic scraping and Google search transformation (Serper-compatible).
- **Stateful Sessions**: Interactive browser sessions via DSL over WebSockets with Taskiq Actors.
- **AI Integration**: Omni-Parser for UI grounding (SoM approach) and local HTML→Markdown conversion (`/html-to-md`).
- **Resource Management**: Inactivity timeout for stateful sessions via `SESSION_INACTIVITY_TIMEOUT` (default 600 s; dev `docker-compose.override.yml` sets 1800 s).
- **Modular Design**: Clean architecture with layers for API, Domain, Infrastructure, and Actions.
- **Docker Production Ready**: Dockerfile with Playwright, docker-compose with api/worker/redis, health endpoint.
- **Anti-Bot Evasion**: Stealth browser pool with User-Agent rotation, proxy integration, human-like interactions.
- **Yandex Maps Extraction**: Extract structured business data (name, address, phone, website, geo coordinates).
- **Site Content Enrichment**: Extract clean text from company websites with optional about/services page crawling.
- **Research Agent**: Autonomous AI research using LangGraph with web search, scraping, and structured report generation.
- **Per-Domain Rate Limiting**: Redis-based token bucket (30/hour for `*.yandex.*`, 1000/hour fallback).

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Async Logic**: Playwright, Taskiq (Redis Broker)
- **AI Tools**: Flexible OpenAI-compatible configuration (LM Studio, OpenAI, etc.) with two logical endpoints (`EXTRACTION_*` and `ORCHESTRATION_*`), Omni-Parser, optional Jina/Reader-LM as the extraction model.
- **Infrastructure**: Redis (Pub/Sub, Taskiq broker and KV store), SearXNG (search backend), Docker

## [Project Structure](STRUCTURE.md)

Detailed directory layout and layer responsibilities are documented in [STRUCTURE.md](STRUCTURE.md).

---

## Quickstart

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- AI Providers: LM Studio (local), OpenAI (cloud), or any OpenAI-compatible API.

### Installation (local dev)

```bash
# 1. Install dependencies
uv sync

# 2. Install Playwright browsers (must use uv run — playwright lives in the venv)
uv run playwright install --with-deps chromium

# 3. Copy and edit environment config
cp .env.example .env
```

Key `.env` values:

```env
API_KEY=default_internal_key          # internal auth header value

EXTRACTION_API_BASE=http://localhost:1234/v1
EXTRACTION_API_KEY=lm-studio
EXTRACTION_MODEL_NAME=jina-reader-lm

ORCHESTRATION_API_BASE=https://api.openai.com/v1
ORCHESTRATION_API_KEY=sk-...
ORCHESTRATION_MODEL_NAME=gpt-4o

REDIS_URL=redis://localhost:6379/0     # Taskiq broker + pub/sub + KV
SESSION_INACTIVITY_TIMEOUT=600         # seconds; dev override sets 1800
```

Full settings list lives in `src/core/config.py` (`pydantic-settings`).

### Proxy Configuration (optional)

Create `proxies.txt` in the project root, one proxy per line in `http://user:pass@host:port` format:

```
http://user:pass@1.2.3.4:8080
http://user:pass@5.6.7.8:8080
```

> **Note for Yandex Maps**: Yandex blocks datacenter proxy IPs at the browser level. Use **residential proxies** (e.g., Bright Data, Oxylabs) to get actual scraping results.

### Docker Production

```bash
# Build and start all services (api, worker, redis)
docker compose up -d

# Check health
curl http://localhost:8000/healthz
# {"status":"healthy", "timestamp":"...", "services":{...}}
# Note: handler always returns 200; the unhealthy/degraded → 503 branch is not implemented today.
```

> `proxies.txt` is automatically bind-mounted into the container if it exists.
> **Important**: create `proxies.txt` before the first `docker compose up`.
> If Docker creates it as a directory (a known Docker Desktop on Windows quirk), run
> `docker compose down && docker compose up -d` to remount correctly.

### Run API without Docker (PM2)

```bash
pm2 start ecosystem.config.js
```

---

## API Reference

All endpoints except `/healthz` require the header `X-API-Key: <API_KEY>`.

### Health

```
GET /healthz
→ 200 {"status": "healthy", "timestamp": "...", "services": {...}}
```

Probes Redis ping + `pool_manager`. Currently always returns 200 (the 503/`degraded` branch documented in spec is not yet wired — see `docs/codebase-report/20-spec-vs-reality.md`, C-09).

### Stateless Atomic Endpoints

```
POST /scraper      {"url": "...", ...}                   # Playwright one-shot page fetch
POST /serper       {"q": "...", "num": 10}               # SERP via SearXNG (Serper-compatible shape)
POST /omni-parse   {"base64_image": "...", "prompt": ""} # OmniParser vision call (via LLM facade)
POST /html-to-md   {"html": "...", ...}                  # local HTML → Markdown / text
```

> The historical `/jina-extract` endpoint from earlier specs is **not implemented** — it was replaced by `/html-to-md` (local conversion via `content_cleaner`).

### Yandex Maps Extraction

```
POST /api/v1/yandex-maps/extract
{
  "category": "restaurants",
  "center": {"lat": 59.934, "lng": 30.306},   // lat ∈ [-90,90], lng ∈ [-180,180]
  "radius": 1000                                // metres, 100–5000
}
→ {"businesses": [...], "total": N, "category": "...", "center": {...}, "radius": N}
```

Each business card: `name`, `address`, and optionally `phone`, `website`, `geo`.

### Site Content Enrichment

```
POST /api/v1/enrich
{
  "url": "https://example.com",
  "crawl_about": false,
  "crawl_services": false
}
→ {"url": "...", "text": "...", "word_count": N, "truncated": bool, "pages_crawled": [...]}
```

Content is truncated to ≤ 500 words. Raw HTML is stripped.

### Research Agent

```
POST /api/v1/research/run
{
  "query": "research topic",
  "mode": "speed" | "balanced" | "quality"   // default: "balanced"
}
→ 202 {"task_id": "...", "status": "pending", "message": "Research task queued"}

GET /api/v1/research/status/{task_id}
→ {"task_id": "...", "status": "completed"|"running"|"failed", "result": {...}, ...}

GET /api/v1/research/stream/{task_id}
→ text/event-stream with progress events
```

The Research Agent uses LangGraph to iteratively search, scrape, and synthesize information into a structured report.

### Rate Limiting

- `*.yandex.*` domains: **30 requests/hour**
- All other domains: **1000 requests/hour**
- Exceeded limit: `429 Too Many Requests` with `Retry-After` header

### Interactive Browser Sessions (DSL)

```
POST /sessions                              → {"session_id": "..."}
POST /sessions/{id}/command  {"type": "goto", "params": {"url": "..."}}
DELETE /sessions/{id}
WS   /ws/{session_id}                       # streaming commands
```

**DSL commands**: `goto`, `scroll`, `click_coord`, `click_omni`, `type`, `screenshot`, `extract_jina`

---

## Testing

```bash
# Full test suite (99 tests, no Docker needed except 2 live E2E tests)
python -m pytest tests/ -q

# Run the two live E2E tests (requires docker compose up)
python -m pytest tests/e2e/test_site_enrichment_flow.py::test_enrichment_returns_clean_text \
                 tests/e2e/test_yandex_maps_full_flow.py::test_yandex_maps_endpoint_returns_businesses -v
```

Test breakdown:

| Suite | Tests | Notes |
|-------|-------|-------|
| unit/ | 17 | No external dependencies |
| contract/ | 28 | In-process FastAPI via `ASGITransport` |
| integration/ | 31 | Mocked browser; Docker config checks |
| e2e/ | 23 | Structural + middleware; 2 hit live `localhost:8000` |

---

## MCP Server

The project includes an MCP (Model Context Protocol) server exposing all web interactions as tools.

Session tools communicate via `POST /sessions/{id}/command` (HTTP) instead of WebSocket — MCP runs over stdio and cannot maintain a persistent WS connection.

### Running

```bash
uv run python -m src.mcp_server
```

### Claude Desktop / OpenCode Configuration

```json
{
  "mcpServers": {
    "atomic-scraper": {
      "command": "uv",
      "args": [
        "run", "--project", "C:/[repo_path]/Atomic-Scraper-Service",
        "python", "C:/[repo_path]/Atomic-Scraper-Service/src/mcp_server.py"
      ],
      "env": {
        "API_KEY": "default_internal_key"
      }
    }
  }
}
```

### Available Tools

- **Stateless**: `scrape`, `search`, `omni_parse`, `jina_extract`
- **Data Extraction**: `yandex_maps_extract`, `enrich_website`
- **Research Agent**: `research_run`, `research_status`, `research_stream`
- **Session Management**: `create_session`, `delete_session`
- **Interactive (DSL)**: `session_goto`, `session_scroll`, `session_click`, `session_type`, `session_screenshot`, `session_click_omni`, `session_extract_jina`

---

## Documentation

- [Project Structure](STRUCTURE.md)
- [Web Interactions (DSL & API)](web_interactions.md)
- [Feature Spec 010 — ML/CV Pipeline](specs/010-scraper-mlcv-prep/spec.md)
- [Implementation Plan 010](specs/010-scraper-mlcv-prep/plan.md)
- [Tasks 010 — 48/48 complete](specs/010-scraper-mlcv-prep/tasks.md)
- [Data Model](specs/010-scraper-mlcv-prep/data-model.md)
- [Quickstart](specs/010-scraper-mlcv-prep/quickstart.md)
