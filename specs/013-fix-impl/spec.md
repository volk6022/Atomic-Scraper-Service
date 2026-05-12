# Feature Specification: Fix Existing Implementations

**Feature Branch**: `013-fix-impl`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: fixing existing implementation: 1) Serper endpoint via Playwright to Google.com with proxy support 2) Sessions with Redis error handling 3) Research Agent via Taskiq 4) Fixed contract tests for real functionality 5) HTML-to-Markdown conversion via markdownify library (replaces jina-extract)

## Clarifications

### Session 2026-05-12

- Q: Who are the primary users of this service? → A: External API Consumers + Internal Agents (Claude, n8n workflows)
- Q: What are the timeout/SLA requirements? → A: Flexible timeouts - 10s for simple endpoints, 900s for complex (LLM-based)
- Q: Authentication requirements? → A: Keep existing X-API-Key only (per Constitution)
- Q: Error response format? → A: Standard format: `{error: string, code: string, details?: object}`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Google Search via Playwright (Priority: P1)

As a developer, I want to perform Google searches through the API so that I can integrate search results into my applications without using third-party paid APIs.

**Why this priority**: The current Serper endpoint returns dummy data and is non-functional. Real search capability is core to the scraping service.

**Independent Test**: Call `/serper` endpoint with a query and verify real Google search results are returned.

**Acceptance Scenarios**:

1. **Given** a valid search query, **When** `/serper` endpoint is called, **Then** the response contains real Google search results with titles, links, and snippets.
2. **Given** a proxy is configured, **When** `/serper` endpoint is called, **Then** the request uses proxy rotation to avoid blocking.
3. **Given** Google blocks the request, **When** `/serper` is called, **Then** the system returns a clear error message indicating blocking.
4. **Given** Redis is unavailable, **When** `/serper` is called, **Then** the endpoint returns 503 Service Unavailable.

---

### User Story 2 - HTML to Markdown Conversion (Priority: P1)

As a developer, I want to convert HTML content to clean Markdown format so that I can process web content for downstream applications.

**Why this priority**: Jina Reader is being removed in favor of the `markdownify` library (per research: markdownify provides better balance of speed and quality). The endpoint needs to be renamed from `/jina-extract` to `/html-to-md`.

**Independent Test**: Call `/html-to-md` endpoint with HTML and verify proper Markdown conversion.

**Acceptance Scenarios**:

1. **Given** HTML content, **When** `/html-to-md` is called, **Then** the response contains clean Markdown converted from the HTML.
2. **Given** complex HTML with scripts/styles, **When** `/html-to-md` is called, **Then** the output contains only meaningful content (scripts/styles removed).
3. **Given** malformed HTML, **When** `/html-to-md` is called, **Then** the system returns a clear error.

---

### User Story 3 - Sessions with Proper Error Handling (Priority: P1)

As a system administrator, I want the session endpoints to handle Redis failures gracefully so that users receive meaningful error messages instead of 500 Internal Server Errors.

**Why this priority**: Current session creation fails with cryptic Redis connection errors instead of proper HTTP error responses.

**Independent Test**: Verify that session endpoints return proper error codes when Redis is unavailable.

**Acceptance Scenarios**:

1. **Given** Redis is unavailable, **When** `POST /sessions` is called, **Then** the response is 503 Service Unavailable with a clear message.
2. **Given** Redis is unavailable, **When** `POST /sessions/{id}/command` is called, **Then** the response is 503 Service Unavailable.
3. **Given** Redis is restored, **When** session operations are performed, **Then** they work normally.
4. **Given** a session is created successfully, **When** commands are executed, **Then** the session actor processes them via Taskiq.

---

### User Story 4 - Research Agent via Taskiq (Priority: P2)

As a researcher, I want the system to autonomously conduct web research and return structured reports so that I can get comprehensive answers to complex questions.

**Why this priority**: The research agent is partially implemented but tasks never execute. Need to wire up Taskiq execution.

**Independent Test**: Submit a research query and verify the task executes and produces a report.

**Acceptance Scenarios**:

1. **Given** a research query, **When** `POST /research/run` is called, **Then** the task is queued and returns 202 with task_id.
2. **Given** a queued research task, **When** Taskiq worker processes it, **Then** the LangGraph executes and produces results.
3. **Given** research completes, **When** `GET /research/status/{task_id}` is called, **Then** the response contains the full research report.
4. **Given** research uses all resources, **When** the deadline or budget is reached, **Then** the system returns a best-effort answer (beast-mode).

---

### User Story 5 - Contract Tests Verify Real Functionality (Priority: P2)

As a developer, I want the test suite to verify actual endpoint behavior so that tests provide meaningful coverage and catch regressions.

**Why this priority**: Current tests create fake placeholder endpoints that always return 200, providing zero verification.

**Independent Test**: Run the test suite and verify all tests exercise real code.

**Acceptance Scenarios**:

1. **Given** contract tests are run, **When** they test `/scraper` or `/serper`, **Then** the tests call the actual router implementations.
2. **Given** tests verify responses, **When** assertions are made, **Then** they check actual response structure and content.
3. **Given** error cases are tested, **When** endpoints fail, **Then** proper error responses are verified.

---

### Edge Cases

- **Serper with all proxies blocked**: Return error with suggestion to add working proxies
- **LLM-extract with LLM timeout**: Return 504 Gateway Timeout with retry hint
- **Session with Redis recovery mid-operation**: Handle reconnection gracefully
- **Research agent with empty search results**: Return partial report with zero citations
- **Contract tests with missing dependencies**: Tests should skip gracefully with clear messages

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `/serper` endpoint that performs real Google searches using headless Playwright browser
- **FR-002**: System MUST support proxy rotation for `/serper` requests to avoid Google blocking
- **FR-003**: System MUST rename `/jina-extract` to `/html-to-md` and use `markdownify` library for HTML-to-Markdown conversion
- **FR-004**: System MUST provide `output_format` parameter for `/html-to-md` (options: markdown, text)
- **FR-005**: System MUST add `output_format` and `clean_html` parameters to `/scraper` endpoint
- **FR-006**: System MUST handle Redis connection failures gracefully in session endpoints with HTTP 503
- **FR-007**: System MUST implement Research Agent execution via Taskiq worker
- **FR-008**: System MUST make `MAX_CONCURRENT_RESEARCH_TASKS` configurable via environment variable
- **FR-009**: All implementation MUST follow **Constitution Principle VI (Test-First)** - tests must verify real behavior
- **FR-010**: Contract tests MUST import and test actual router implementations, not placeholders

### Key Entities

- **SearchResult**: Represents a Google search result with title, link, snippet, position
- **HtmlToMdRequest**: Request for HTML to Markdown conversion with html content and output_format
- **HtmlToMdResponse**: Response with converted markdown content
- **ResearchTask**: Async task for web research with status tracking
- **ResearchReport**: Final output with answer, citations, facts, statistics

---

## Success Criteria *(mandatory)*

### Non-Functional Requirements

- **NFR-001**: Simple endpoints (scraper, serper, sessions) MUST complete within 10 seconds
- **NFR-002**: Complex endpoints with LLM (llm-extract ~3s, research) MUST complete within 900 seconds
- **NFR-003**: Failed requests MUST return appropriate HTTP status codes (4xx, 5xx) with clear error messages
- **NFR-004**: All protected endpoints MUST use X-API-Key authentication (per Constitution)
- **NFR-005**: Error responses MUST use standard format: `{error: string, code: string, details?: object}`

### Measurable Outcomes

- **SC-001**: `/serper` endpoint returns real Google search results for valid queries
- **SC-002**: `/serper` respects proxy rotation and handles blocking gracefully
- **SC-003**: `/html-to-md` returns clean Markdown converted from HTML
- **SC-004**: Session endpoints return 503 (not 500) when Redis is unavailable
- **SC-005**: Research tasks execute within their configured deadline and always produce output
- **SC-006**: All contract tests exercise real code paths with meaningful assertions
- **SC-007**: Test suite runs successfully with `python -m pytest tests/ -q`

---

## Assumptions

- Playwright browsers are installed and functional
- Redis is used for Taskiq task queue (assumed available in production)
- Google Search via Playwright may require residential proxies for reliability
- `markdownify` library provides reliable HTML-to-Markdown conversion
