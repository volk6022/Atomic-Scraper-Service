# Quickstart: Auto-Research Agent

**Branch**: `011-auto-research-agent` | **Date**: 2026-05-11

## Overview

The Auto-Research Agent accepts natural-language research questions and produces structured markdown reports with cited sources. It runs asynchronously via Taskiq workers.

## Prerequisites

- Docker and docker-compose running
- API key: `default_internal_key` (from `.env`)
- Redis available (via docker-compose)

## Running the Service

```bash
# Start the full stack
docker compose up -d

# Verify health
curl http://localhost:8000/healthz
```

## Using the Research Agent

### Submit a Research Task

```bash
curl -X POST http://localhost:8000/api/v1/research/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: default_internal_key" \
  -d '{"query": "What are the latest trends in electric vehicle batteries?"}'
```

**Response** (202 Accepted):

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Research task queued"
}
```

### Poll for Results

```bash
curl http://localhost:8000/api/v1/research/status/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: default_internal_key"
```

**Response** (200 OK):

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "answer_markdown": "...",
    "citations": [...],
    "facts": [...],
    "stats": {...}
  }
}
```

### Using Different Modes

```json
{"query": "quick fact", "mode": "speed"}
{"query": "standard research", "mode": "balanced"}
{"query": "deep analysis", "mode": "quality"}
```

### Overriding Limits

```json
{
  "query": "my question",
  "max_iterations": 15,
  "max_tokens": 20000
}
```

## Testing

### Run Contract Tests

```bash
python -m pytest tests/contract/test_research_endpoint.py -v
```

### Run Unit Tests

```bash
python -m pytest tests/unit/research/ -v
```

### Run Integration Tests

```bash
python -m pytest tests/integration/test_research_graph.py -v
```

### Run All Tests

```bash
python -m pytest tests/ -q
```

## Expected Test Results (TDD Phase)

Before implementation, tests should be **RED**:

- `tests/contract/test_research_endpoint.py`: Tests fail - endpoints don't exist yet
- `tests/unit/research/test_modes.py`: Tests fail - mode presets not implemented
- `tests/unit/research/test_nodes.py`: Tests fail - graph nodes not implemented
- `tests/unit/research/test_state_transitions.py`: Tests fail - router logic not implemented
- `tests/integration/test_research_graph.py`: Tests fail - graph not compiled

After implementation, all tests should pass **GREEN**.

## Architecture Overview

```
POST /research/run → Taskiq → LangGraph → [search → scrape → extract → answer]
                                      ↑
                              Loop safety constraints
                              (budget, deadline, stall)
                                      ↓
GET /research/status/{id} ← Redis ← Result
```

## Configuration

| Setting | Environment Variable | Default |
|---------|---------------------|---------|
| API Key | `API_KEY` | `default_internal_key` |
| Max Concurrent per Key | (hardcoded) | 3 |
| Task TTL | (hardcoded) | 24 hours |

## Troubleshooting

**429 Too Many Requests**: You have >5 concurrent research tasks. Wait for one to complete.

**404 Not Found**: Task expired (24h) or invalid ID.

**Task stuck running**: Check Taskiq worker logs - may need to restart workers: `docker compose restart api`