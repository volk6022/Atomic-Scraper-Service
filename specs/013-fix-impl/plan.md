# Implementation Plan: Fix Existing Implementations

**Branch**: `013-fix-impl` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-fix-impl/spec.md`

## Summary

Fix and complete existing implementation gaps in Atomic Scraper Service:
1. Implement real Google search via Playwright (Serper endpoint) with proxy support
2. Replace Jina Reader with `markdownify` library (HTML-to-Markdown endpoint)
3. Add Redis error handling to session endpoints (HTTP 503 instead of 500)
4. Wire up Research Agent execution via Taskiq
5. Fix contract tests to verify real functionality

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, Playwright, Taskiq, Redis, Pydantic v2, httpx, LangGraph, LangChain  
**Storage**: Redis (task queues), in-memory task store (24h retention)  
**Testing**: pytest, pytest-asyncio  
**Target Platform**: Linux server (Docker container)  
**Project Type**: Backend web-service (REST API + MCP)  
**Performance Goals**: Simple endpoints <10s, LLM endpoints ~3s (jinaai.readerlm-v2), research <900s  
**Constraints**: X-API-Key auth (existing), standard error format `{error, code, details}` (NFR-005)  
**Scale/Scope**: 5 user stories, 10 functional requirements

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Dual-Context Isolation**: Serper is stateless (Playwright pool), sessions are stateful (Taskiq actors) - respects split
- [x] **II. AI Orchestration**: HTML-to-MD uses markdownify (no LLM), Research Agent uses LLMFacade for classification/extraction
- [x] **III. Resource Lifecycle**: Session endpoints now handle Redis failures with proper timeouts
- [x] **IV. Architecture**: Code changes fit existing API/Domain/Infrastructure/Actions layers
- [x] **V. DSL Integration**: SearchClient becomes a new infrastructure client, not a DSL action
- [x] **VI. Test-First**: FR-009/FR-010 mandate TDD - contract tests must import real routers
- [x] **VII. Backend-Only**: No frontend components - pure REST API
- [x] **VIII. Production Deployment**: Uses existing Dockerfile, docker-compose, /healthz endpoint
- [x] **IX. Anti-Bot Mitigation**: Serper via Playwright adds proxy rotation for Google search
- [x] **X. Autonomous Research Agent**: Research Agent wires Taskiq execution, reuses existing scraping tools

> **Resolution**: All Constitution principles satisfied. Phase 0 research complete - markdownify library selected for HTML-to-Markdown conversion.

## Project Structure

### Documentation (this feature)

```text
specs/013-fix-impl/
├── plan.md              # This file
├── research.md          # Phase 0 output: LM Studio structured output testing
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

Changes to existing structure:

```text
src/
├── api/
│   ├── routers/
│   │   ├── stateless.py          # MODIFY: Add output_format/clean_html params, rename /jina-extract → /html-to-md
│   │   └── sessions.py           # MODIFY: Add Redis error handling (503)
│   └── main.py                   # Verify routes updated
├── domain/
│   └── models/
│       └── requests.py           # MODIFY: Add output_format, clean_html to ScrapeRequest, rename JinaExtractRequest → HtmlToMdRequest
├── infrastructure/
│   ├── browser/
│   │   └── pool_manager.py      # MODIFY: Add method for search context creation
│   └── external_api/
│       └── search_client.py      # MODIFY: Real Google search via Playwright
├── actions/
│   └── research/
│       ├── __init__.py          # MODIFY: Add Taskiq task execution
│       └── tools.py              # MODIFY: Use real search client instead of fake URLs
└── infrastructure/
    └── queue/
        └── broker.py            # MODIFY: Add research task queue

tests/
├── contract/
│   ├── test_stateless.py        # REWRITE: Import real routers, test actual endpoints
│   ├── test_html_to_md.py       # RENAME: from test_analysis.py, test /html-to-md
│   └── test_research_endpoint.py # MODIFY: Test real Taskiq execution
└── integration/
    ├── test_google_search.py    # NEW: Serper via Playwright integration
    └── test_session_redis_failure.py # NEW: Redis error handling
```

**Structure Decision**: Single project structure at repository root. Changes extend existing `src/api/`, `src/infrastructure/`, `src/actions/`, `src/domain/` modules.

## Phase 0: Research Results

### Research: HTML-to-Markdown Approach (COMPLETE)

**Library Selected**: `markdownify`

**Rationale**:
- Jina Reader removed per user decision
- `markdownify` provides fast, reliable HTML-to-Markdown conversion
- No external API dependencies required
- Clean output without LLM overhead

**Implementation**:
```python
from markdownify import markdownify

def html_to_markdown(html: str) -> str:
    return markdownify(html)
```

**Output Formats**:
- `markdown` (default): Full Markdown conversion
- `text`: Plain text with line breaks preserved

### Research: Google Search via Playwright

**Approach**: Headless browser navigation to google.com

**Steps**:
1. Create Playwright context with proxy (if configured)
2. Navigate to `https://www.google.com/search?q={query}`
3. Wait for search results to load
4. Extract: titles (h3), links (div a[href]), snippets (div[style])
5. Return SearchResult[]

**Selectors (to verify during implementation)**:
- Titles: `h3`
- Links: `div a[href^="/url?q="]`
- Snippets: `div[data-sncf]`

## Complexity Tracking

> No violations identified. All Constitution principles satisfied.

---

*Plan created: 2026-05-12*
*Phase 0 research: COMPLETE*
*Feature status: Ready for Phase 1 (design) and Phase 2 (tasks)*

---

## Deliverables

### API Endpoints Modified
- `POST /scraper` - Add output_format, clean_html parameters
- `POST /serper` - Real Google search via Playwright
- `POST /html-to-md` - Rename from /jina-extract, use markdownify library
- `POST /sessions` - Handle Redis failure with 503
- `POST /sessions/{id}/command` - Handle Redis failure with 503

### Key Implementation Files
- `src/infrastructure/external_api/search_client.py` - Google search via Playwright
- `src/api/routers/sessions.py` - Redis error handling
- `src/api/routers/stateless.py` - Updated params, renamed endpoint
- `src/actions/research/__init__.py` - Taskiq task execution
- `src/domain/utils/content_cleaner.py` - Add html_to_markdown() using markdownify

### New Dependencies
- `markdownify` - HTML to Markdown conversion

### Tests to Create/Fix
- `tests/contract/test_stateless.py` - Rewrite with real routers
- `tests/contract/test_html_to_md.py` - Rename from test_analysis.py, test /html-to-md
- `tests/integration/test_google_search.py` - Serper integration
- `tests/integration/test_session_redis_failure.py` - Redis error handling
