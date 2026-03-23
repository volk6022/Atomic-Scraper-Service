# Atomic Scraper Service

High-throughput atomic scraping and stateful interactive browser sessions with LLM orchestration.

## Features
- **Stateless Scraper**: Fast atomic scraping and Google search transformation (Serper-compatible).
- **Stateful Sessions**: Interactive browser sessions via DSL over WebSockets with Taskiq Actors.
- **AI Integration**: Omni-Parser for UI grounding (SoM approach) and Jina Reader for structured markdown extraction.
- **Resource Management**: Automatic 10-minute inactivity timeout for stateful sessions.
- **Modular Design**: Clean architecture with layers for API, Domain, Infrastructure, and Actions.

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Async Logic**: Playwright, Taskiq (Redis Broker)
- **AI Tools**: Flexible OpenAI-compatible configuration (LM Studio, OpenAI, etc.), Jina Reader V2, Omni-Parser
- **Infrastructure**: Redis (Pub/Sub and Task Queue), Docker

## [Project Structure](STRUCTURE.md)
Detailed directory layout and layer responsibilities are documented in [STRUCTURE.md](STRUCTURE.md).

## Quickstart

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AI Providers: LM Studio (local), OpenAI (cloud), or any OpenAI-compatible API.

### Installation
1.  **Clone and Setup**:
    ```bash
    uv init .
    uv sync
    ```
2.  **Environment Variables**:
    Create a `.env` file from `.env.example`. This service uses separate configurations for **Extraction** (e.g., Jina Reader LM) and **Orchestration** (e.g., Reasoning/Navigation):
    ```env
    # Extraction Settings (e.g., Local LM Studio)
    EXTRACTION_API_BASE=http://localhost:1234/v1
    EXTRACTION_API_KEY=lm-studio
    EXTRACTION_MODEL_NAME=jina-reader-lm

    # Orchestration Settings (e.g., OpenAI)
    ORCHESTRATION_API_BASE=https://api.openai.com/v1
    ORCHESTRATION_API_KEY=sk-...
    ORCHESTRATION_MODEL_NAME=gpt-4o
    ```
3.  **Start Infrastructure**:
    ```bash
    docker-compose up -d
    ```
4.  **Run API**:
    ```bash
    uv run python -m src.api.main
    ```

### Usage
- **Atomic Scrape**: `POST /scraper` with `{"url": "..."}`
- **Interactive Session**: `POST /sessions` to get `session_id`, then connect via `ws:///ws/{session_id}`.

## Testing
Run the full test suite (including contract and integration tests):
```bash
uv run python -m pytest tests
```

## Documentation
- [Tasks](specs/009-smart-scraping-llm-api/tasks.md)
- [Implementation Plan](specs/009-smart-scraping-llm-api/plan.md)
- [Research Findings](specs/009-smart-scraping-llm-api/research.md)
- [Data Model](specs/009-smart-scraping-llm-api/data-model.md)
