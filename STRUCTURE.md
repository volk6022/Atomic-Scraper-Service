# Project Structure: Atomic Scraper Service

This document provides an overview of the directory structure and the purpose of each component in the Atomic Scraper Service.

```text
src/
├── api/                           # [Presentation Layer] REST & WebSockets
│   ├── routers/                   # Endpoint definitions (stateless, sessions)
│   │   ├── stateless.py           # Atomic scraper, search, analysis endpoints
│   │   ├── sessions.py            # Session lifecycle + POST /sessions/{id}/command
│   │   ├── health.py              # /healthz endpoint (FR-003)
│   │   ├── yandex_maps.py        # /api/v1/yandex-maps/extract (FR-006)
│   │   └── enrichment.py         # /api/v1/enrich endpoint (FR-007)
│   ├── websockets/                # WebSocket communication logic
│   │   ├── handler.py             # WebSocket connection handler
│   │   └── manager.py             # Redis Pub/Sub coordination for WebSockets
│   ├── middleware/                # API middleware
│   │   ├── auth.py                # Authentication middleware (Static API Key)
│   │   └── rate_limit.py         # Per-domain rate limiting (FR-009, FR-010)
│   └── main.py                    # FastAPI application entry point
│
├── domain/                        # [Domain Layer] Business Logic & Models
│   ├── models/                    # Pydantic models for requests and DSL
│   │   ├── requests.py            # API request/response models
│   │   ├── dsl.py                 # DSL command and session models
│   │   ├── business_card.py      # Yandex Maps business card model
│   │   ├── enriched_content.py   # Site enrichment model (FR-007)
│   │   └── rate_limit_rule.py    # Rate limit rule model (FR-009)
│   ├── utils/                     # Domain utilities
│   │   └── content_cleaner.py    # HTML cleaning, text extraction (FR-007, FR-008)
│   └── registry/                  # Action Registry for DSL command mapping
│       └── action_registry.py
│
├── infrastructure/                # [Infrastructure Layer] External integrations
│   ├── browser/                   # Playwright browser management
│   │   ├── pool_manager.py        # Global browser process and context pool
│   │   ├── stealth_pool.py        # Stealth browser wrapper (FR-004)
│   │   ├── user_agent_pool.py     # User-Agent rotation pool (FR-004)
│   │   ├── proxy_provider.py      # Proxy selection and management
│   │   └── session_manager.py     # Inactivity tracking for stateful sessions
│   ├── external_api/              # Clients for external services
│   │   ├── clients/               # Specific provider implementations
│   │   │   └── openai_client.py   # Generic OpenAI-compatible client
│   │   ├── facade.py              # LLM Facade for extraction and orchestration
│   │   ├── jina_client.py         # Jina Reader client (placeholder)
│   │   ├── omni_client.py         # Omni-Parser client (placeholder)
│   │   └── search_client.py       # Google Search transformation logic
│   ├── rate_limiter/             # Per-domain rate limiting
│   │   └── token_bucket.py        # Redis-based token bucket (FR-009)
│   └── queue/                     # Task queue and background workers
│       ├── broker.py              # Taskiq Redis broker configuration
│       ├── workers.py             # General Taskiq task definitions
│       ├── session_actor.py       # Isolated browser session actor
│       └── cleanup_worker.py      # Background session cleanup task
│
├── actions/                       # [Actions Layer] DSL Implementation logic
│   ├── base.py                    # Base action definition
│   ├── navigation.py              # Browser navigation actions (goto, scroll)
│   ├── interaction.py             # UI interaction actions (click, fill)
│   ├── extraction.py              # Data extraction actions (screenshot, DOM)
│   ├── ai_actions.py              # AI-enhanced actions (Omni-click, Jina-extract)
│   ├── yandex_maps.py             # Yandex Maps extraction action (FR-006)
│   └── site_enricher.py           # Site content enrichment action (FR-007)
│
├── core/                          # [Cross-cutting] Configuration & Utils
│   ├── config.py                  # Pydantic settings management
│   └── logging.py                 # Centralized logging configuration
│
tests/                             # [Tests] Test suite
├── unit/                          # Business logic and unit tests
│   ├── test_stealth_browser.py    # FR-004: Stealth capabilities
│   ├── test_rate_limiter.py      # FR-009, FR-010: Rate limiting
│   └── test_content_cleaner.py   # FR-007, FR-008: Site enrichment
├── contract/                      # API contract verification tests
│   ├── test_yandex_maps_api.py   # FR-006: Yandex Maps extraction
│   ├── test_health_endpoint.py   # FR-003: Health check
│   └── test_enrichment_api.py    # FR-007: Enrichment endpoint
├── integration/                   # Component integration tests
│   ├── test_docker_compose.py    # FR-001, FR-002: Docker integration
│   ├── test_proxy_integration.py # FR-005: Proxy pool integration
│   └── test_yandex_extraction.py # FR-006: Yandex Maps extraction
└── e2e/                           # End-to-end tests
    ├── test_yandex_maps_full_flow.py  # US3: Full extraction flow
    ├── test_site_enrichment_flow.py   # US4: Full enrichment flow
    └── test_docker_deployment.py      # US1: Docker deployment
```

## Layers Overview

1.  **Presentation (api)**: Handles HTTP and WebSocket communication, request validation, and response formatting.
2.  **Domain (domain)**: Defines the core data structures, DSL commands, and the registry of available actions.
3.  **Infrastructure (infrastructure)**: Bridges the application with external systems (Browsers, LLMs, Redis).
4.  **Actions (actions)**: Contains the implementation logic for each DSL command, interacting directly with Playwright `Page` objects.
5.  **Cross-cutting (core)**: Manages global configuration, secrets, and logging.

## Feature 010-scraper-mlcv-prep Components

| Feature | Files | Requirements |
|---------|-------|--------------|
| Docker | Dockerfile, docker-compose.yml | FR-001, FR-002, FR-003 |
| Stealth Browser | stealth_pool.py, user_agent_pool.py | FR-004, FR-005 |
| Yandex Maps | yandex_maps.py, business_card.py | FR-006 |
| Site Enrichment | site_enricher.py, content_cleaner.py, enrichment.py | FR-007, FR-008 |
| Rate Limiting | token_bucket.py, rate_limit.py, rate_limit_rule.py | FR-009, FR-010 |
