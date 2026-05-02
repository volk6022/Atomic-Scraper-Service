# Quickstart: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature**: 010-scraper-mlcv-prep  
**Date**: 2026-05-01

---

## Prerequisites

- Python 3.11+
- Redis 7.x
- Docker (for containerized deployment)
- Playwright browsers installed

---

## Local Development Setup

### 1. Install Dependencies

```bash
cd repos/Atomic-Scraper-Service
uv sync
uv run playwright install chromium
```

### 2. Start Redis

```bash
docker compose up -d redis
# Or: redis-server --daemonize yes
```

### 3. Copy Environment Variables

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 4. Run the Service

```bash
# Terminal 1: API server
uv run python -m src.api.main

# Terminal 2: Worker
uv run taskiq worker src.infrastructure.queue.broker:broker src.infrastructure.queue.tasks
```

---

## Docker Deployment

### 1. Build Image

```bash
docker build -t atomic-scraper-service:latest .
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

### 3. Verify Health

```bash
curl http://localhost:8000/healthz
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-05-01T12:00:00Z",
  "services": {
    "redis": "connected",
    "browser_pool": "available"
  }
}
```

---

## API Usage Examples

### Health Check

```bash
curl http://localhost:8000/healthz
```

### Yandex Maps Extraction

```bash
curl -X POST http://localhost:8000/scrape/yandex-maps \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "category": "restaurants",
    "center": {"lat": 59.934, "lng": 30.306},
    "radius": 1000,
    "use_stealth": true
  }'
```

### Site Enrichment

```bash
curl -X POST http://localhost:8000/enrich/site \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "url": "https://company.example.com",
    "crawl_pages": ["about", "services"],
    "max_words": 500
  }'
```

---

## Testing

### Run Tests (TDD - tests must fail first)

```bash
# Run unit tests
pytest tests/unit/ -v

# Run contract tests
pytest tests/contract/ -v

# Run integration tests
pytest tests/integration/ -v

# Run E2E tests
pytest tests/e2e/ -v
```

### Test Files Structure (per TDD Requirements)

```
tests/
├── unit/
│   ├── test_stealth_browser.py
│   ├── test_rate_limiter.py
│   └── test_content_cleaner.py
├── contract/
│   ├── test_yandex_maps_api.py
│   ├── test_health_endpoint.py
│   └── test_enrichment_api.py
├── integration/
│   ├── test_docker_compose.py
│   ├── test_proxy_integration.py
│   └── test_yandex_extraction.py
└── e2e/
    ├── test_yandex_maps_full_flow.py
    ├── test_site_enrichment_flow.py
    └── test_docker_deployment.py
```

---

## Rate Limiting

The service enforces per-domain rate limits:

| Domain Pattern | Limit |
|----------------|-------|
| `*.yandex.*` | 30 requests/hour |
| `*` (default) | 1000 requests/hour |

When rate limited, API returns:
- Status: 429 Too Many Requests
- Header: `Retry-After: <seconds>`

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Static API key for authentication | (required) |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `RATE_LIMIT_YANDEX_PER_HOUR` | Rate limit for Yandex domains | `30` |

### Proxy Configuration

Place proxy list in `proxies.txt`:
```
http://proxy1.example.com:8080
http://user:pass@proxy2.example.com:8080
```

---

## Troubleshooting

### Health check fails

1. Check Redis: `redis-cli ping` → should return PONG
2. Check browser: Ensure Chromium is installed
3. Check logs: `uv run python -m src.api.main` for errors

### Rate limit errors

- Verify you're not exceeding 30 req/hour for Yandex
- Check rate limit headers: `X-RateLimit-Remaining`

### Yandex Maps blocked

- Ensure `use_stealth: true` in request
- Consider using proxy rotation
- Check logs for detection errors

---

## Next Steps

1. Run tests to verify TDD implementation
2. Implement features following tasks.md
3. Verify all success criteria in spec.md