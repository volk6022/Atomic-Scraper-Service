# Atomic Scraper OS

Smart Scraping API with LLM-orchestration and Stateful Actors.

## Features
- **Stateless Pool:** Fast atomic scraping with server-side proxy rotation.
- **Stateful Actors:** Interactive browser sessions controlled via WebSockets.
- **LLM Orchestration:** Integrated with OpenAI (Structured Output), Jina Reader V2, and Omni-Parser.
- **Clean Architecture:** Strictly decoupled domain, infrastructure, and presentation layers.
- **Resilience:** Automatic inactivity timeouts and resource cleanup for stateful sessions.

## Tech Stack
- **Framework:** FastAPI
- **Automation:** Playwright
- **Task Queue:** Taskiq + Redis
- **AI:** OpenAI GPT-4o, Jina Reader V2, Omni-Parser

## Quick Start

1. **Start Redis:**
   ```bash
   docker-compose up -d
   ```

2. **Install Dependencies:**
   ```bash
   uv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

4. **Run API:**
   ```bash
   uvicorn scraper_os.api.main:app --reload
   ```

4. **Run Worker:**
   ```bash
   taskiq worker scraper_os.infrastructure.queue.broker:broker
   ```

## Documentation
- [Endpoints Guide](ENDPOINTS.md)
- [Architecture & Structure](STRUCTURE.md)
