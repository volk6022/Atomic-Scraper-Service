# Quickstart: Fix Existing Implementations

**Feature**: `013-fix-impl`
**Created**: 2026-05-12

## Overview

This document provides quick reference for the new/changed functionality.

---

## 1. Google Search via Playwright (`/serper`)

```bash
curl -X POST http://localhost:8000/serper \
  -H "X-API-Key: default_internal_key" \
  -H "Content-Type: application/json" \
  -d '{"q": "python web scraping", "num": 5}'
```

**Response**:
```json
{
  "searchParameters": {"q": "python web scraping", "type": "search"},
  "organic": [
    {"title": "Scrapy | A Fast and Powerful Scraping...", "link": "https://scrapy.org/", "snippet": "...", "position": 1}
  ],
  "total": 5
}
```

**Proxy support**:
```bash
curl -X POST http://localhost:8000/serper \
  -H "X-API-Key: default_internal_key" \
  -d '{"q": "test", "proxy": "http://user:pass@proxy:8080"}'
```

---

## 2. HTML to Markdown Conversion (`/html-to-md`)

Convert HTML to clean Markdown using the `markdownify` library.

```bash
curl -X POST http://localhost:8000/html-to-md \
  -H "X-API-Key: default_internal_key" \
  -H "Content-Type: application/json" \
  -d '{
    "html": "<html><head><title>Test</title></head><body><p>Content</p></body></html>",
    "format": "markdown"
  }'
```

**Response**:
```json
{
  "content": "# Test\n\nContent"
}
```

---

## 3. Scraper with HTML Cleaning

```bash
# Clean HTML (remove scripts/styles) - uses ContentCleaner
curl -X POST http://localhost:8000/scraper \
  -H "X-API-Key: default_internal_key" \
  -d '{"url": "https://example.com", "clean_html": true}'

# Text output - strips all HTML tags
curl -X POST http://localhost:8000/scraper \
  -H "X-API-Key: default_internal_key" \
  -d '{"url": "https://example.com", "output_format": "text"}'

# Markdown output - uses markdownify library
curl -X POST http://localhost:8000/scraper \
  -H "X-API-Key: default_internal_key" \
  -d '{"url": "https://example.com", "output_format": "markdown"}'
```

---

## 4. Sessions with Redis Error Handling

### Create Session
```bash
curl -X POST http://localhost:8000/sessions \
  -H "X-API-Key: default_internal_key"
```

**Success** (201):
```json
{"session_id": "abc123", "status": "starting", "message": "Session created"}
```

**Redis Unavailable** (503):
```json
{
  "error": "Session creation temporarily unavailable - Redis connection failed",
  "code": "REDIS_UNAVAILABLE",
  "details": {"redis_host": "localhost", "redis_port": 6379}
}
```

---

## 5. Research Agent (Taskiq Execution)

```bash
# Start research
curl -X POST http://localhost:8000/api/v1/research/run \
  -H "X-API-Key: default_internal_key" \
  -d '{"query": "What are the latest trends in AI?", "mode": "balanced"}'

# Response (202):
{"task_id": "task_xyz", "status": "pending", "message": "Research task queued"}

# Check status
curl http://localhost:8000/api/v1/research/status/task_xyz \
  -H "X-API-Key: default_internal_key"
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_RESEARCH_TASKS` | 5 | Max concurrent research tasks per API key |
| `ORCHESTRATION_MODEL_NAME` | gpt-4o | Model for Research Agent |

### proxies.txt

One proxy per line for Serper/Google search:
```
http://user:pass@proxy1:8080
http://user:pass@proxy2:8080
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| `REDIS_UNAVAILABLE` | Redis connection failed (503) |
| `PROXY_ALL_BLOCKED` | All proxies blocked Google (502) |
| `INVALID_REQUEST` | Request validation failed (422) |

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# Run specific test suites
python -m pytest tests/contract/ -v
python -m pytest tests/integration/test_google_search.py -v
python -m pytest tests/integration/test_html_to_md.py -v
python -m pytest tests/integration/test_session_redis_failure.py -v
```
