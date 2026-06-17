# API Contract: Research Endpoints

**Branch**: `011-auto-research-agent` | **Date**: 2026-05-11

## Overview

The Auto-Research Agent exposes two REST endpoints for asynchronous research task submission and status polling.

## Authentication

All endpoints require `X-API-Key: <API_KEY>` header (same as existing protected endpoints).

## Endpoints

### POST /api/v1/research/run

Submit a new research task.

**Request**:

```http
POST /api/v1/research/run
Content-Type: application/json
X-API-Key: default_internal_key
```

```json
{
  "query": "What are the latest trends in electric vehicle batteries?",
  "mode": "balanced",
  "max_iterations": null,
  "max_tokens": null
}
```

**Fields**:

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | 3-2000 chars |
| `mode` | string | No | "balanced" | "speed", "balanced", "quality" |
| `max_iterations` | integer | No | null | 1-20 |
| `max_tokens` | integer | No | null | 1000-32000 |

**Response - 202 Accepted**:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Research task queued"
}
```

**Error Responses**:

- 401 Unauthorized: Missing or invalid API key
- 422 Unprocessable Entity: Invalid request body (invalid mode, query too short/long, etc.)
- 429 Too Many Requests: More than 5 concurrent tasks for this API key

---

### GET /api/v1/research/status/{task_id}

Poll for task status and retrieve results.

**Request**:

```http
GET /api/v1/research/status/550e8400-e29b-41d4-a716-446655440000
X-API-Key: default_internal_key
```

**Response - 200 OK (In Progress)**:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": {
    "phase": "searching",
    "percent": 40,
    "message": "Searching for relevant sources..."
  },
  "created_at": "2026-05-11T12:00:00Z"
}
```

**Response - 200 OK (Completed)**:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "answer_markdown": "Electric vehicle batteries are trending toward [1] higher energy density and [2] faster charging capabilities...",
    "citations": [
      {
        "url": "https://example.com/ev-battery-trends",
        "title": "EV Battery Trends 2026",
        "snippet": "New solid-state batteries promise 2x energy density..."
      }
    ],
    "facts": [
      {
        "claim": "Solid-state batteries promise 2x energy density",
        "confidence": 0.85,
        "source_url": "https://example.com/ev-battery-trends"
      }
    ],
    "stats": {
      "iterations": 5,
      "urls_visited": 12,
      "elapsed_seconds": 184.5,
      "mode_used": "balanced",
      "completed_normally": true
    }
  },
  "created_at": "2026-05-11T12:00:00Z",
  "updated_at": "2026-05-11T12:03:04Z"
}
```

**Response - 200 OK (Failed/Degraded)**:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "answer_markdown": "Unable to gather sufficient data. Partial findings: ...",
    "citations": [],
    "facts": [],
    "stats": {
      "iterations": 10,
      "urls_visited": 0,
      "elapsed_seconds": 300.0,
      "mode_used": "balanced",
      "completed_normally": false
    }
  }
}
```

**Error Responses**:

- 401 Unauthorized: Missing or invalid API key
- 404 Not Found: Task ID does not exist or has expired

---

### GET /api/v1/research/stream/{task_id} (Optional)

Server-Sent Events for real-time progress. This endpoint is optional - polling works without it.

**Request**:

```http
GET /api/v1/research/stream/550e8400-e29b-41d4-a716-446655440000
X-API-Key: default_internal_key
```

**Event Stream**:

```text
event: node_entered
data: {"node": "classify", "timestamp": "2026-05-11T12:00:01Z"}

event: node_exited
data: {"node": "classify", "elapsed_ms": 150, "timestamp": "2026-05-11T12:00:01Z"}

event: progress
data: {"phase": "searching", "percent": 20}

event: completed
data: {"task_id": "..."}
```

## Rate Limiting

- Maximum 5 concurrent research tasks per API key
- Exceeding this returns 429 with `Retry-After` header

## Task Expiration

- Completed tasks retained for 24 hours after completion
- After 24 hours, GET returns 404 (task expired)

## Testing Contracts

These contracts are validated by:

- `tests/contract/test_research_endpoint.py`: API contract tests
- `tests/integration/test_research_graph.py`: Full graph integration tests
- `tests/unit/research/test_modes.py`: Mode preset unit tests
- `tests/unit/research/test_nodes.py`: Node transformation unit tests
- `tests/unit/research/test_state_transitions.py`: Router truth table tests