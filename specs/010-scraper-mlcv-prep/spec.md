# Feature Specification: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature Branch**: `010-scraper-mlcv-prep`  
**Created**: 2026-05-01  
**Status**: Draft  
**Input**: User description: "REVIEW-auto-monitor-ml-cv.md - prepare Atomic-Scraper-Service for ML/CV pipeline (Docker + Yandex Maps stealth + site enrichment)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Docker Production Readiness (Priority: P1)

As a DevOps engineer, I need the service to be containerized with proper health checks, so that it can be deployed reliably in production environments alongside Redis and worker processes.

**Why this priority**: Without Docker readiness, the service cannot be integrated into the auto-monitor-ml-cv pipeline's production infrastructure. This blocks all downstream use cases.

**Independent Test**: Can be fully tested by building the Docker image, starting all services via docker-compose, and verifying the health endpoint returns 200.

**Acceptance Scenarios**:

1. **Given** a Dockerfile exists, **When** `docker build` is executed, **Then** the image builds successfully with Playwright browser dependencies included.
2. **Given** docker-compose is configured with api, worker, and redis services, **When** `docker compose up` is executed, **Then** all services start and remain running.
3. **Given** the service is running in Docker, **When** a health check request is sent to `/healthz`, **Then** the endpoint returns 200 OK within acceptable latency.

---

### User Story 2 - Anti-Bot Evasion for Yandex Maps (Priority: P1)

As a data engineer, I need the scraper to bypass Yandex Maps anti-bot protections, so that I can collect business data (name, address, phone, website, coordinates) for the ML/CV client-acquisition pipeline.

**Why this priority**: Yandex Maps is a primary data source for US6. Without stealth capabilities, the service will be blocked within minutes, making the entire pipeline unusable.

**Independent Test**: Can be tested by sending 30+ scrape requests to Yandex Maps and verifying that at least 80% return valid data (not blocked/429).

**Acceptance Scenarios**:

1. **Given** a request to scrape Yandex Maps, **When** stealth mode is enabled, **Then** the request returns valid HTML rather than a block/429 response.
2. **Given** multiple scrape requests, **When** User-Agent rotation is enabled, **Then** each request uses a different User-Agent from the configured pool.
3. **Given** a request with a proxy specified, **When** the proxy is available, **Then** the request is routed through the specified proxy.
4. **Given** a request without explicit proxy, **When** proxy provider is integrated, **Then** the system optionally selects a proxy from the pool.

---

### User Story 3 - Yandex Maps Business Data Extraction (Priority: P1)

As a data engineer, I need the service to extract structured business data from Yandex Maps based on location parameters, so that I can populate the ML/CV pipeline's company database.

**Why this priority**: This is the core data collection mechanism for US6. Without a dedicated Yandex Maps extractor, manual DSL commands would be required for each request, making the pipeline non-viable.

**Independent Test**: Can be tested by sending a request with (category, center coordinates, radius) and verifying the response contains a list of business cards with name/address/phone/website/geo.

**Acceptance Scenarios**:

1. **Given** category "restaurants", center [59.934, 30.306], radius 1000m, **When** a Yandex Maps extraction request is sent, **Then** the response contains a list of at least 10 business cards with name and address.
2. **Given** a business card in the response, **When** data is present, **Then** it includes at minimum: name, address, and optionally phone/website/coordinates.
3. **Given** pagination is required to collect all results, **When** the extraction runs, **Then** the system handles scroll-based pagination to collect all businesses within the radius.

---

### User Story 4 - Site Content Enrichment (Priority: P2)

As a marketing operations specialist, I need the scraper to extract clean text from company websites, so that I can use the content for personalizing cold outreach emails in the ML/CV pipeline.

**Why this priority**: US7 requires enriching company data with clean text content. Raw HTML is not usable for LLM-based personalization.

**Independent Test**: Can be tested by sending a company URL and verifying the response contains cleaned text (≤500 words) suitable for content analysis.

**Acceptance Scenarios**:

1. **Given** a valid company website URL, **When** an enrichment request is sent, **Then** the response contains cleaned text extracted from the main page.
2. **Given** a URL that supports about/services pages, **When** enrichment is requested, **Then** the system crawls additional pages and includes relevant content.
3. **Given** the extracted content exceeds 500 words, **When** enrichment completes, **Then** the content is truncated to approximately 500 words.
4. **Given** the page contains HTML formatting, **When** enrichment completes, **Then** the output is plain text or markdown (not raw HTML).

---

### User Story 5 - Per-Domain Rate Limiting (Priority: P2)

As a system administrator, I need the service to enforce rate limits per domain, so that the pipeline respects Yandex Maps Terms of Service (30 requests/hour) and avoids getting blocked.

**Why this priority**: The auto-monitor-ml-cv constitution specifies 30 req/h for `*.yandex.*` domains. Without rate limiting, the pipeline would violate ToS and get blocked.

**Independent Test**: Can be tested by sending 35 requests to Yandex Maps within one hour and verifying subsequent requests are rejected or delayed.

**Acceptance Scenarios**:

1. **Given** more than 30 requests to `*.yandex.*` within one hour, **When** another request is sent, **Then** the system rejects the request with a rate limit error.
2. **Given** a request to a non-restricted domain, **When** the request is sent, **Then** the system processes it without rate limit restrictions.
3. **Given** the rate limit window has passed, **When** a new request is sent, **Then** the system processes it normally.

---

### Edge Cases

- **Proxy Failure**: If the selected proxy is unavailable or returns an error, the system MUST attempt the request with an alternative proxy or fall back to direct connection.
- **Content Too Large**: If the extracted site content exceeds reasonable memory limits, the system MUST return an error rather than consuming excessive resources.
- **JavaScript-Heavy Pages**: If the target page requires extensive JavaScript execution, the system MUST wait for network idle before extracting content.
- **Robots.txt Compliance**: The system SHOULD respect robots.txt directives when extracting site content.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a Dockerfile based on Playwright Python image that includes all browser dependencies.
- **FR-002**: System MUST provide docker-compose configuration that includes api, worker, and redis services with proper networking.
- **FR-003**: System MUST provide a `/healthz` endpoint that returns 200 OK when the service is running and healthy.
- **FR-004**: System MUST provide stealth browser capabilities including User-Agent rotation and human-like interaction patterns.
- **FR-005**: System MUST integrate proxy provider into the browser pool so that requests can use proxies from the pool automatically.
- **FR-006**: System MUST provide a Yandex Maps extraction action that accepts (category, center coordinates, radius) and returns a list of business cards.
- **FR-007**: System MUST provide a site enrichment action that extracts clean text from company websites, including optional crawling of about/services pages.
- **FR-008**: System MUST truncate enriched content to approximately 500 words.
- **FR-009**: System MUST provide per-domain rate limiting with configurable limits (default 30/hour for `*.yandex.*`).
- **FR-010**: System MUST return appropriate errors when rate limits are exceeded.

### Key Entities

- **Business Card**: Represents a business listing from Yandex Maps with name, address, phone, website, and geo coordinates.
- **Enriched Content**: Represents cleaned and truncated text content extracted from a company website.
- **Rate Limit Rule**: Represents a domain pattern and associated request limit (count per time window).
- **Proxy**: Represents a proxy server with host, port, and authentication credentials.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can deploy the service using Docker and have all components (api, worker, redis) running within 5 minutes of `docker compose up`.
- **SC-002**: The `/healthz` endpoint responds within 200ms when the service is healthy.
- **SC-003**: Yandex Maps extraction achieves at least 80% success rate (non-blocked responses) over 30 requests within an hour.
- **SC-004**: Site enrichment returns cleaned text content (not raw HTML) with content length ≤500 words for 95% of successful extractions.
- **SC-005**: Rate limiting correctly blocks requests to `*.yandex.*` after 30 requests within any 1-hour window.
- **SC-006**: The service can handle at least 10 concurrent scrape requests without degradation.

---

## TDD Requirements *(mandatory - per Constitution Principle VI)*

This feature MUST be implemented following the **Test-First Implementation** mandate from the Atomic Scraper Service Constitution (v1.4.0, Principle VI).

### TDD Cycle Requirements

- **FR-TDD-001**: All functional requirements (FR-001 through FR-010) MUST have corresponding failing test cases BEFORE any implementation code is written.
- **FR-TDD-002**: Implementation is PERMITTED ONLY after the test suite is ready to verify the "Green" state.
- **FR-TDD-003**: All new Actions MUST be verified with Playwright mocks before implementation.
- **FR-TDD-004**: E2E tests MUST verify the full flow from API request to browser action for each feature.

### Test Types Required

| Test Type | Coverage Required |
|-----------|-------------------|
| **Unit Tests** | Each function/method in isolation with mocked dependencies |
| **Contract Tests** | API request/response schemas, DSL command/result formats |
| **Integration Tests** | Component interactions (browser pool, rate limiter, etc.) |
| **E2E Tests** | Full user flows from acceptance scenarios |

### Test Files Structure

```
tests/
├── unit/
│   ├── test_stealth_browser.py      # FR-004: Stealth capabilities
│   ├── test_rate_limiter.py        # FR-009, FR-010: Rate limiting
│   └── test_content_cleaner.py     # FR-007, FR-008: Site enrichment
├── contract/
│   ├── test_yandex_maps_api.py     # FR-006: Yandex Maps extraction contract
│   ├── test_health_endpoint.py     # FR-003: Health check contract
│   └── test_enrichment_api.py      # FR-007: Enrichment endpoint contract
├── integration/
│   ├── test_docker_compose.py      # FR-001, FR-002: Docker integration
│   ├── test_proxy_integration.py  # FR-005: Proxy pool integration
│   └── test_yandex_extraction.py   # FR-006: Yandex Maps extraction
└── e2e/
    ├── test_yandex_maps_full_flow.py      # US3: Full extraction flow
    ├── test_site_enrichment_flow.py       # US4: Full enrichment flow
    └── test_docker_deployment.py          # US1: Docker deployment
```

### Red-Green-Refactor Enforcement

1. **Red Phase**: Write failing tests for each requirement. Tests MUST fail until implementation is complete.
2. **Green Phase**: Write minimum implementation to make tests pass.
3. **Refactor Phase**: Clean up code while maintaining test pass status.

**No implementation code allowed until test files exist with failing tests for all FRs.**

---

## Assumptions

- The upstream maintainer (volk6022) is willing to accept contributions for Yandex Maps and stealth features.
- The auto-monitor-ml-cv pipeline will use this service via REST API or MCP tools.
- Yandex Maps ToS allows scraping for the pipeline's use case (business data collection for cold outreach).
- Python 3.11+ will remain the target runtime version.