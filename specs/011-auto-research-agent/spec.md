# Feature Specification: Auto-Research Agent

**Feature Branch**: `011-auto-research-agent`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "add auto-research agent"

---

## Test-First Approach *(mandatory)*

Per **Constitution Principle VI**, every user story begins with failing tests that define the expected outcome *before* any implementation code is written. This section maps each story to its required test contracts — these tests MUST be authored and verified as RED before the corresponding implementation phase begins.

| Story | Test Type | What the Failing Test Proves | File (to create) |
|-------|-----------|------------------------------|------------------|
| US1 | Contract | POST/GET endpoint shape, auth, 202+task_id, final report schema | `tests/contract/test_research_endpoint.py` |
| US2 | Unit | Mode presets produce correct state initialization | `tests/unit/research/test_modes.py` |
| US3 | Unit | Beast-mode trips at 85% budget, stall counter increments on zero-new-URL, answer always produced | `tests/unit/research/test_nodes.py` |
| US3 | Integration | Graph terminates within max_iters, emits valid ResearchReport, tiny budget forces beast-mode but still produces answer | `tests/integration/test_research_graph.py` |
| US1 | Unit | Each node transforms state correctly (gaps shrink, visited grows, facts accumulate) | `tests/unit/research/test_nodes.py` |
| US1 | Unit | State transition router truth table (continue/stop conditions) | `tests/unit/research/test_state_transitions.py` |
| US4 | Integration | SSE events emitted in order during graph traversal | `tests/integration/test_research_graph.py` |
| US4 | Contract | GET /research/stream endpoint delivers events as emitted | `tests/contract/test_research_endpoint.py` |

**Gate rule**: No implementation file is written until at least one corresponding test file exists and can be executed (producing a RED/failing result).

---

## Clarifications

### Session 2026-05-11

- Q: Maximum concurrent research tasks allowed per API key? → A: Max 5 concurrent tasks per API key, reject with 429 if exceeded
- Q: Observability — what operational signals does the research agent emit? → A: Node-level structured log records — emit log at each graph-node boundary (entered, exited, elapsed) plus warnings for stalls and budget thresholds
- Q: Which internal search tools should the research agent use? → A: Google web search + Yandex Maps, but Yandex Maps only when user explicitly requests local/geo research

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit Research Query and Receive Report (Priority: P1)

A user submits a natural-language research question (e.g., "What are the latest trends in electric vehicle batteries?"). The system autonomously searches the web, scrapes relevant pages, extracts key facts, and returns a structured report with cited sources.

**Why this priority**: This is the core value proposition — turn a question into a cited research report. Without this, nothing else matters.

**TDD Contract**: Before a single line of action code is written, the following must be in place and RED:

- **Contract test** (`tests/contract/test_research_endpoint.py`):
  - `POST /research/run` with valid body + API key → `202 {task_id}`
  - `POST /research/run` without API key → `401`
  - `POST /research/run` with invalid mode → `422`
  - `POST /research/run` when API key already has 5 running tasks → `429`
  - `GET /research/status/{task_id}` after completion → final ResearchReport with answer_markdown, citations, facts, stats fields populated
  - `GET /research/status/{fake_id}` → appropriate not-found response
- **Unit test** (`tests/unit/research/test_nodes.py`): Each graph node (classify, plan, search, rank_dedupe, scrape, extract_facts, reflect, answer, writer) transforms its input state slice correctly.
- **Unit test** (`tests/unit/research/test_state_transitions.py`): The router function returns the correct next node for every state combination (gaps empty, beast_mode=True, iter ≥ max_iters, etc.).

**Acceptance Scenarios**:

1. **Given** the service is running, **When** a user sends `POST /research/run` with a valid query and API key, **Then** the system returns `202` with a task ID for polling.
2. **Given** a submitted research task, **When** the user polls `GET /research/status/{task_id}`, **Then** the system returns the current phase and progress until the final report is ready.
3. **Given** a completed research task, **When** the user retrieves the final result, **Then** the response includes: a markdown answer with numbered citations, a list of citations with URLs and titles, extracted facts with confidence scores, and execution statistics (iterations, URLs visited, elapsed time, mode used).

---

### User Story 2 - Choose Research Depth by Mode (Priority: P2)

A user selects one of three research modes — speed, balanced, or quality — each trading off speed against depth and completeness.

**Why this priority**: Different use cases demand different depth levels. A quick fact check shouldn't wait minutes; a comprehensive report justifies longer runtimes.

**TDD Contract**:

- **Unit test** (`tests/unit/research/test_modes.py`):
  - Mode preset values verified: max_iters, search_k, scrape_concurrency, token_budget, deadline differ for speed/balanced/quality
  - Mode → state initialization produces correct defaults
  - User-supplied overrides (max_tokens, max_iters) take precedence over mode defaults

**Acceptance Scenarios**:

1. **Given** a user, **When** they submit a query with mode "speed", **Then** the system completes within seconds, visiting fewer sources, and returns a concise answer.
2. **Given** a user, **When** they submit a query with mode "balanced", **Then** the system iterates through multiple search/scrape cycles and returns a moderately detailed report within a few minutes.
3. **Given** a user, **When** they submit a query with mode "quality" for a decomposable query, **Then** the system may break the question into sub-questions, research each independently, and synthesize findings into a comprehensive report.
4. **Given** an invalid mode value, **When** submitted, **Then** the system rejects the request with a clear error indication (422).

---

### User Story 3 - Guaranteed Completion with Graceful Degradation (Priority: P2)

Even if research hits resource limits (time, data volume, new-source exhaustion), the system MUST always return a best-effort answer rather than failing silently or hanging indefinitely.

**Why this priority**: Trust requires reliability. Users submitting long-running research must never face abandoned tasks or indefinite hangs.

**TDD Contract**:

- **Unit test** (`tests/unit/research/test_nodes.py`):
  - `tokens_used >= 85% of token_budget` → `beast_mode` flips to `True`
  - `time > deadline_ts` → `beast_mode` flips to `True`
  - `stall_counter >= 2` → `beast_mode` flips to `True`
  - Zero new URLs after ranking → `stall_counter` increments by 1
  - Beast-mode routing: goes to `answer_node` (skips plan/search/scrape/extract-facts)
- **Integration test** (`tests/integration/test_research_graph.py`):
  - Full graph compiled with a `FakeChatModel` and stub tools
  - Graph terminates within mode's `max_iters`
  - Emits a valid `ResearchReport` with ≥1 citation
  - Tiny token_budget → beast_mode triggers → answer still produced

**Acceptance Scenarios**:

1. **Given** a research task approaching its time limit, **When** the deadline is reached, **Then** the system stops further exploration and synthesizes a report from whatever facts have been collected so far.
2. **Given** a research task that has exhausted all discoverable new sources, **When** repeated search cycles return only already-visited URLs, **Then** the system detects the stall and proceeds to report generation.
3. **Given** any failure condition during research (scrape error, extraction failure, partial data), **When** the task completes, **Then** the final report always contains a valid response — even if marked as degraded — and never returns an error instead of a report.

---

### User Story 4 - Monitor Research Progress in Real Time (Priority: P3)

A user wants to observe the research agent's decision-making as it happens — which sources are being visited, what facts are extracted, when a stall or deadline is triggered.

**Why this priority**: Valuable for debugging, transparency, and long-running deep analysis tasks. Not essential for basic usage.

**TDD Contract**:

- **Integration test** (`tests/integration/test_research_graph.py`):
  - Graph traversal emits node events in expected order (classify → plan → search → rank → scrape → extract → reflect)
  - SSE endpoint delivers events as they are emitted from each node

**Acceptance Scenarios**:

1. **Given** an active research task, **When** a user connects to the event stream endpoint, **Then** they receive a stream of milestone events as the agent progresses through its research graph.
2. **Given** a completed research task, **When** event streaming is not used, **Then** all other functionality remains unaffected (streaming is optional).

---

### Edge Cases

- What happens when the user submits a query in a language the system cannot process well?
- What happens when search returns zero results for a query?
- What happens when all discovered URLs fail to load or time out during scraping?
- What happens when the user polls a task ID that does not exist?
- What happens when report results expire from storage before the user retrieves them?
- What happens when concurrent research tasks are submitted by multiple users?
- What happens when extracted facts from different sources contradict each other?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept natural-language research queries via an API endpoint requiring authentication.
- **FR-002**: System MUST return a task identifier immediately (within 1 second) and process research asynchronously.
- **FR-003**: System MUST support three research modes: speed, balanced, and quality with distinct depth/time tradeoffs.
- **FR-004**: System MUST conduct web searches using Google web search via its own search capabilities without external third-party search APIs.
- **FR-005**: System MUST scrape discovered web pages using its own scraping infrastructure, extracting clean text content.
- **FR-006**: System MUST extract factual claims from scraped pages, each with a source URL and confidence indication.
- **FR-007**: System MUST produce a markdown-formatted research report containing: a synthesized answer with numbered citations, a list of cited sources (URL, title, snippet), extracted facts with confidence scores, and execution statistics.
- **FR-008**: System MUST enforce a maximum execution time per mode, after which exploration stops and a best-effort report is generated — the task MUST never be abandoned or left hanging.
- **FR-009**: System MUST detect when new search results contain only previously visited URLs and stop further exploration (stall detection).
- **FR-010**: System MUST track and report execution statistics: iterations, URLs visited, elapsed time, and whether the task completed normally or was cut short.
- **FR-011**: System MUST provide a polling endpoint for task status and final report retrieval.
- **FR-012**: System MUST reject requests with invalid modes or missing required fields (422).
- **FR-013**: System MUST allow users to optionally override default limits (max iterations, max tokens) per request.
- **FR-014**: System MUST store completed reports retrievable for a reasonable period after completion.
- **FR-015**: System MUST classify incoming queries by type (factoid, comparative, exploratory, decomposable) to determine appropriate research strategy.
- **FR-016**: System MUST handle contradictory facts from different sources by noting disagreements in the final report.
- **FR-017**: All implementation MUST follow **Constitution Principle VI (Test-First)** — every code file is preceded by a failing test file per the TDD Contract table in this spec.
- **FR-018**: System MUST fit within existing architecture layers per **Constitution Principle IV (Clean Architecture Boundaries)**.
- **FR-019**: System MUST follow **Constitution Principle X (Autonomous Research Agent)** — LangGraph orchestration, loop safety, tool reuse.
- **FR-020**: System MUST limit concurrent research tasks to a maximum of 5 per API key and reject additional submissions with 429 (Too Many Requests).
- **FR-021**: System MUST emit structured log records at each graph-node boundary (entered, exited, elapsed) plus warnings when stall detection or budget thresholds are approached.
- **FR-022**: System MAY use Yandex Maps for local/geo-specific research, but only when the user's query explicitly requests location-based or business-discovery research; Yandex Maps MUST NOT be auto-selected by query classification alone.

### Key Entities

- **Research Request**: A user-submitted query with a selected mode and optional constraint overrides (max iterations, max tokens).
- **Research Task**: An active or completed research job with a unique task ID, current phase, progress indicators, and eventual result.
- **Research Report**: The final output containing a markdown answer, citations list, extracted facts, and execution statistics.
- **Citation**: A referenced source with URL, page title, and content snippet used in the report.
- **Fact**: An extracted claim from a specific source with a confidence score and source URL.
- **Research Stats**: Execution metadata including iteration count, URLs visited, time elapsed, mode used, and whether the task was cut short.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users receive a task ID within 1 second of submitting a research query.
- **SC-002**: Quick-mode queries complete within 2 minutes for typical factoid questions.
- **SC-003**: Balanced-mode queries complete within 5 minutes for typical comparative questions.
- **SC-004**: Deep analysis mode completes within 20 minutes for complex decomposable queries.
- **SC-005**: 100% of submitted research tasks produce a final report — zero abandoned or hung tasks — regardless of errors or resource limits encountered.
- **SC-006**: Every research report includes at least one cited source when search results are available.
- **SC-007**: Users can submit and retrieve research results knowing only their query and preferred depth level, with no technical configuration required.
- **SC-008**: The system correctly handles 5 concurrent research tasks without degradation in individual task response time.
- **SC-009**: All tests in the TDD Contract table pass BEFORE declaring the feature complete — no implementation file ships without a corresponding test file.

## Assumptions

- The service already has working web search, page scraping, and content extraction capabilities that the research agent reuses.
- User authentication uses the same API key mechanism (`X-API-Key` header) as all other protected endpoints.
- Completed research reports are stored with a default 24-hour retention period.
- The system uses a local AI backend that is already configured and available.
- Research modes default to "balanced" when not explicitly specified by the user.