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
### Run API (PM2)
To run the service with PM2, including the background workers:
```bash
pm2 start ecosystem.config.js
```

### Manual Testing
You can use the provided `test_ws.py` to verify the WebSocket session and DSL commands:
1. Ensure the server is running.
2. Install test dependencies: `pip install websockets httpx`.
3. Run the test: `python test_ws.py`.

## Testing
Run the full test suite (including contract and integration tests):
```bash
uv run python -m pytest tests
```

## MCP Server

The project includes an MCP (Model Context Protocol) server that exposes all web interactions as tools for LLMs.

Session tools (`session_goto`, `session_screenshot`, etc.) communicate with the backend via **`POST /sessions/{session_id}/command`** — a regular HTTP endpoint — instead of WebSocket. This is intentional: MCP runs over stdio and cannot maintain a persistent WS connection. The WebSocket endpoint (`/ws/{session_id}`) remains available for other clients.

### Running the MCP Server
To run the MCP server manually from any directory:
```bash
cd C:/[repo_path]/Atomic-Scraper-Service && uv run python -m src.mcp_server
```

### Claude Desktop / OpenCode Configuration
Add this to your `claude_desktop_config.json` (or equivalent MCP config):
```json
{
  "mcpServers": {
    "atomic-scraper": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "C:/[repo_path]/Atomic-Scraper-Service",
        "python",
        "C:/[repo_path]/Atomic-Scraper-Service/src/mcp_server.py"
      ],
      "env": {
        "API_KEY": "your_internal_key"
      }
    }
  }
}
```

### Available Tools
- **Stateless**: `scrape`, `search`, `omni_parse`, `jina_extract`
- **Session Management**: `create_session`, `delete_session`
- **Interactive (DSL)**: `session_goto`, `session_scroll`, `session_click`, `session_type`, `session_screenshot`, `session_click_omni`, `session_extract_jina`

## JSON DSL Guide

The JSON DSL controls browser sessions. Commands can be sent two ways:

### Option A: HTTP (recommended for MCP / programmatic clients)
1. **Start a Session**: `POST /sessions` (requires `X-API-Key`) -> returns `session_id`.
2. **Send Commands**: `POST /sessions/{session_id}/command` with body `{"type": "<command>", "params": { ... }}`.
3. **Result** is returned directly in the HTTP response (blocks up to 60 s).

### Option B: WebSocket (recommended for interactive / streaming clients)
1. **Start a Session**: `POST /sessions` -> returns `session_id`.
2. **Connect**: `ws://localhost:8000/ws/{session_id}`.
3. **Send Commands**: Send JSON frames `{"type": "<command>", "params": { ... }}`. Results arrive as push frames on the same connection.

### Core Commands
- **`goto`**: `{"url": "https://..."}` - Navigate to a URL.
- **`scroll`**: `{"direction": "down", "amount": 500}` - Scroll the page.
- **`click_coord`**: `{"x": 0.5, "y": 0.2}` - Click relative coordinates.
- **`type`**: `{"selector": "input", "text": "hello"}` - Type into a selector.
- **`screenshot`**: `{}` - Capture base64 screenshot.

### AI-Enhanced
- **`click_omni`**: `{"element_description": "the login button"}` - AI-based grounding.
- **`extract_jina`**: `{"extraction_schema": {...}}` - Structured extraction.

## Documentation
- [Web Interactions (DSL & API)](web_interactions.md)
- [Tasks](specs/009-smart-scraping-llm-api/tasks.md)
- [Implementation Plan](specs/009-smart-scraping-llm-api/plan.md)
- [Research Findings](specs/009-smart-scraping-llm-api/research.md)
- [Data Model](specs/009-smart-scraping-llm-api/data-model.md)
