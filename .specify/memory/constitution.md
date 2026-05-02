<!--
Sync Impact Report
Version change: 1.3.0 → 1.4.0
List of modified principles:
  - Added: VIII. Production Deployment Readiness
  - Added: IX. Anti-Bot Detection Mitigation
Added sections:
  - VIII. Production Deployment Readiness (Core Principles)
  - IX. Anti-Bot Detection Mitigation (Core Principles)
Removed sections:
  - None
Templates requiring updates:
  - ✅ updated: .specify/templates/plan-template.md (Constitution Check section)
  - ⚠ pending: .specify/templates/spec-template.md (TDD already enforced, no changes needed)
  - ⚠ pending: .specify/templates/tasks-template.md (no changes needed)
Follow-up TODOs:
  - TODO(RATIFICATION_DATE): Original adoption date unknown - remains from v1.3.0
-->
# Atomic Scraper Service Constitution

## Core Principles

### I. Dual-Context Isolation (Stateless/Stateful)
The system MUST maintain a strict separation between Stateless Pool workers and Stateful Actor workers. Stateless workers handle atomic scraping/search tasks with a shared persistent browser instance, while Stateful Actors manage long-running interactive sessions with dedicated browser instances and WebSocket-based command loops. This ensures high throughput for simple tasks and high reliability for complex ones.

### II. Unified AI Orchestration Facade
All interactions with Large Language Models (LLMs) and Vision-Language Models (VLMs), including Jina Reader, Omni-Parser, and OpenAI, MUST be channeled through the `LLMFacade`. This centralization ensures consistent prompt engineering, structured output handling, and simplified swapping of provider implementations without impacting business logic.

### III. Resource Lifecycle Governance
Stateful sessions MUST implement a mandatory inactivity timeout. If no commands are received via WebSocket within the configured `SESSION_TIMEOUT_SECONDS`, the Actor MUST force-close the browser and terminate its process. This prevents memory leaks and resource exhaustion in long-running scraper sessions.

### IV. Clean Architecture Boundaries
Code MUST be organized into isolated layers: API (Presentation), Domain (Models/DSL), Infrastructure (External/Browser), and Actions (Commands). Communication between layers MUST be unidirectional and follow established patterns (Registry, Facade) to ensure testability and maintainability.

### V. Command-Driven Interaction (DSL)
Interactive sessions MUST be driven by a Domain Specific Language (DSL) defined in `CommandPayload`. Every action (navigation, extraction, AI-decision) MUST be a discrete, registry-backed class that operates on a Playwright page. This ensures predictable behavior and enables easy extension of system capabilities.

### VI. Test-First Implementation (TDD Mandatory)
Tests MUST be generated and established before any functional code is written. Every feature, action, or bug fix MUST start with failing test cases (unit, contract, or integration) that define the expected outcome. Functional implementation is only permitted once the test suite is ready to verify the "Green" state.

### VII. Backend-Only Focus (No Frontend)
This project is a pure backend service. Development MUST NOT include any frontend components, web interfaces, or browser-rendered dashboards (excluding generated API documentation). All functionality MUST be exposed via REST and WebSocket APIs only.

### VIII. Production Deployment Readiness
The system MUST be production-ready with containerization support. This includes: (a) a Dockerfile based on Playwright-compatible image with all browser dependencies; (b) docker-compose configuration that includes api, worker, and redis services with proper networking; (c) a `/healthz` endpoint that returns 200 OK when the service is healthy. This ensures the service can be deployed reliably in production environments alongside Redis and worker processes.

### IX. Anti-Bot Detection Mitigation
The system MUST provide capabilities to mitigate anti-bot detection when scraping target websites. This includes: (a) stealth browser capabilities such as User-Agent rotation and human-like interaction patterns; (b) integrated proxy pool support that can be optionally applied to requests; (c) per-domain rate limiting with configurable limits (e.g., default 30/hour for `*.yandex.*` domains). These capabilities enable the service to collect data from sites with anti-bot protections without immediate blocking.

## Technical Constraints
- **Concurrency**: Use `asyncio` for I/O bound tasks (Network, Playwright) and separate processes (Taskiq) for isolation.
- **Data Exchange**: Use Redis Pub/Sub for real-time command/result routing between FastAPI and Stateful Actors.
- **Infrastructure Orchestration**: Redis and other persistent shared services MUST be managed via `docker-compose`. Developers and CI/CD pipelines MUST use the project's `docker-compose.yml` to ensure consistent environment parity.
- **Stateless Stability**: The global Playwright instance in Stateless workers MUST remain active for the duration of the worker process to minimize context creation overhead.

## Development Workflow
- **Spec First**: Features MUST be defined in `.specify/templates/spec-template.md` before implementation.
- **Test-Driven Cycle**: Follow the Red-Green-Refactor cycle. Tests must fail first, then implementation makes them pass, followed by cleanup.
- **Testing Discipline**: New Actions MUST be verified with Playwright mocks. E2E tests MUST verify the full flow from WebSocket command to browser action.
- **Documentation**: Every directory MUST contain a `doc.md` explaining its responsibility and key patterns.

## Governance
This Constitution is the primary authority for architectural and procedural decisions. Any deviations MUST be documented in the Implementation Plan's "Complexity Tracking" section and justified against these principles.

**Versioning Policy**:
- MAJOR: Removal or redefinition of core principles (e.g., merging Stateless/Stateful).
- MINOR: Addition of new architectural constraints or guidance.
- PATCH: Refinements, clarifications, or documentation fixes.

**Compliance**: All PRs MUST be reviewed against this constitution. Automated linting and type-checking (mypy/ruff) are mandatory for all contributions.

**Version**: 1.4.0 | **Ratified**: TODO(RATIFICATION_DATE) | **Last Amended**: 2026-05-01