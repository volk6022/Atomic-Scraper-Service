# Project Structure: Atomic Scraper Service

This document provides an overview of the directory structure and the purpose of each component in the Atomic Scraper Service.

```text
src/
├── api/                           # [Presentation Layer] REST & WebSockets
│   ├── routers/                   # Endpoint definitions (stateless, sessions)
│   │   ├── stateless.py           # Atomic scraper, search, analysis endpoints
│   │   └── sessions.py            # Session lifecycle + POST /sessions/{id}/command
│   ├── websockets/                # WebSocket communication logic
│   │   ├── handler.py             # WebSocket connection handler
│   │   └── manager.py             # Redis Pub/Sub coordination for WebSockets
│   ├── auth.py                    # Authentication middleware (Static API Key)
│   └── main.py                    # FastAPI application entry point
│
├── domain/                        # [Domain Layer] Business Logic & Models
│   ├── models/                    # Pydantic models for requests and DSL
│   │   ├── requests.py            # API request/response models
│   │   └── dsl.py                 # DSL command and session models
│   └── registry/                  # Action Registry for DSL command mapping
│       └── action_registry.py
│
├── infrastructure/                # [Infrastructure Layer] External integrations
│   ├── browser/                   # Playwright browser management
│   │   ├── pool_manager.py        # Global browser process and context pool
│   │   ├── proxy_provider.py      # Proxy selection and management
│   │   └── session_manager.py     # Inactivity tracking for stateful sessions
│   ├── external_api/              # Clients for external services
│   │   ├── clients/               # Specific provider implementations
│   │   │   └── openai_client.py   # Generic OpenAI-compatible client
│   │   ├── facade.py              # LLM Facade for extraction and orchestration
│   │   ├── jina_client.py         # Jina Reader client (placeholder)
│   │   ├── omni_client.py         # Omni-Parser client (placeholder)
│   │   └── search_client.py       # Google Search transformation logic
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
│   └── ai_actions.py              # AI-enhanced actions (Omni-click, Jina-extract)
│
├── core/                          # [Cross-cutting] Configuration & Utils
│   ├── config.py                  # Pydantic settings management
│   └── logging.py                 # Centralized logging configuration
│
tests/                             # [Tests] Test suite
├── contract/                      # API contract verification tests
├── integration/                   # Component integration tests (Redis, Playwright)
└── unit/                          # Business logic and unit tests
```

## Layers Overview

1.  **Presentation (api)**: Handles HTTP and WebSocket communication, request validation, and response formatting.
2.  **Domain (domain)**: Defines the core data structures, DSL commands, and the registry of available actions.
3.  **Infrastructure (infrastructure)**: Bridges the application with external systems (Browsers, LLMs, Redis).
4.  **Actions (actions)**: Contains the implementation logic for each DSL command, interacting directly with Playwright `Page` objects.
5.  **Cross-cutting (core)**: Manages global configuration, secrets, and logging.
