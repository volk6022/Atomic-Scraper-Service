# Quickstart: Smart Scraper Service

## Prerequisites
- Docker & Docker Compose
- API Keys: OpenAI, Serper (optional), Jina

## Setup
1. Clone the repository.
2. Create a `.env` file:
   ```env
   API_KEY=your_internal_key
   OPENAI_API_KEY=sk-...
   JINA_API_KEY=jina_...
   REDIS_URL=redis://localhost:6379
   ```
3. Define your proxy pool in `proxies.yaml`:
   ```yaml
   proxies:
     - http://user:pass@proxy1.com
     - http://user:pass@proxy2.com
   ```
4. Start the services:
   ```bash
   docker-compose up -d
   ```

## Usage Examples

### 1. Simple Scrape
```bash
curl -X POST http://localhost:8000/scraper \
  -H "X-API-Key: your_internal_key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://google.com"}'
```

### 2. Interactive Session
1. Create session:
   ```bash
   curl -X POST http://localhost:8000/sessions ...
   ```
2. Connect to WebSocket:
   `ws://localhost:8000/ws/{session_id}`
3. Send Command:
   `{"action": "goto", "params": {"url": "https://news.ycombinator.com"}}`
