# Data Model: Fix Existing Implementations

**Feature**: `013-fix-impl`
**Created**: 2026-05-12

## Overview

This document describes the data models affected by the implementation changes.

---

## Modified: ScrapeRequest

**Location**: `src/domain/models/requests.py`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | HttpUrl | Yes | - | Target URL to scrape |
| `proxy` | Optional[str] | No | None | Proxy URL (http://user:pass@host:port) |
| `wait_until` | WaitUntil | No | DOM_CONTENT_LOADED | Playwright wait condition |
| `clean_html` | bool | No | False | Remove scripts, styles, comments |
| `output_format` | Literal["html", "text", "markdown"] | No | "html" | Output format |

**Conversion Logic**:
- `clean_html=True`: Use ContentCleaner (strip scripts/styles/nav)
- `output_format="text"`: Strip all HTML tags
- `output_format="markdown"`: Use `markdownify` library for HTML → Markdown

**Validation**:
- `url` must be a valid HTTP/HTTPS URL
- `wait_until` must be one of: domcontentloaded, load, networkidle

---

## Modified: SearchRequest / SearchResponse

**Location**: `src/domain/models/requests.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | str | Yes | Search query |
| `num` | int | No (default: 10) | Number of results (1-100) |

**Response Model**:

| Field | Type | Description |
|-------|------|-------------|
| `searchParameters` | dict | Original search parameters |
| `organic` | List[SearchResult] | Real search results |
| `total` | int | Total number of results |

---

## New: SearchResult

**Location**: `src/domain/models/requests.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | str | Yes | Result title |
| `link` | str | Yes | Result URL |
| `snippet` | str | No | Result description snippet |
| `position` | int | Yes | Position in search results |

---

## Renamed: LLMExtractRequest (formerly JinaExtractRequest)

**Location**: `src/domain/models/requests.py`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `html` | str | Yes | HTML content to extract from |
| `extraction_schema` | Optional[dict] | No | JSON Schema for extraction |
| `prompt` | Optional[str] | No | Custom extraction instruction |

**Extraction via**: `jinaai.readerlm-v2` model at LM Studio

**Schema in System Prompt Format**:
```json
{
  "type": "object",
  "properties": {
    "field_name": {"type": "string"},
    ...
  }
}
```

---

## Modified: Session Endpoints

**Location**: `src/api/routers/sessions.py`

### Create Session Response

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | str | Unique session identifier |
| `status` | str | "starting" or "active" |
| `message` | Optional[str] | Status message |

### Error Response (Redis unavailable)

| Field | Type | Description |
|-------|------|-------------|
| `error` | str | Human-readable error message |
| `code` | str | Error code: "REDIS_UNAVAILABLE" |
| `details` | Optional[dict] | Additional error details |

### HTTP Status Codes

| Scenario | Status Code |
|----------|-------------|
| Success | 201 Created |
| Redis unavailable | 503 Service Unavailable |
| Invalid request | 422 Unprocessable Entity |
| Auth failure | 401 Unauthorized |

---

## Research Agent Models

**Location**: `src/domain/models/research.py`

### ResearchRequest

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | str | Yes | Research question |
| `mode` | Literal["speed", "balanced", "quality"] | No (default: balanced) | Research depth |
| `max_iterations` | Optional[int] | No | Override iteration limit |
| `max_tokens` | Optional[int] | No | Override token budget |

### ResearchReport

| Field | Type | Description |
|-------|------|-------------|
| `answer_markdown` | str | Markdown report with citations |
| `citations` | List[Citation] | Source list |
| `facts` | List[Fact] | Extracted facts with confidence |
| `stats` | ResearchStats | Execution statistics |
| `degraded` | bool | True if beast-mode triggered |

---

## Standard Error Response

**Format**: `{error: string, code: string, details?: object}`

| Field | Type | Description |
|-------|------|-------------|
| `error` | str | Human-readable error |
| `code` | str | Machine-readable error code |
| `details` | Optional[dict] | Additional context |

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `REDIS_UNAVAILABLE` | 503 | Redis connection failed |
| `PROXY_ALL_BLOCKED` | 502 | All proxies blocked |
| `LLM_TIMEOUT` | 504 | LLM extraction timeout |
| `INVALID_REQUEST` | 422 | Request validation failed |
| `AUTH_FAILED` | 401 | Invalid API key |
