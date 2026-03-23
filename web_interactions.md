# Web Interactions: Atomic Scraper Service

This document describes the available interaction methods, their JSON models, and intended usage.

## 1. Stateless REST API

Fast, atomic operations that do not require a persistent browser session.

### `POST /scraper`
Scrapes the full HTML content of a URL.
- **Model**: `ScrapeRequest`
```json
{
  "url": "https://example.com",
  "proxy": "http://user:pass@host:port",
  "wait_until": "domcontentloaded"
}
```
- **Response**: `ScrapeResponse`
```json
{
  "id": "uuid-v4",
  "url": "https://example.com",
  "content": "<html>...</html>",
  "status": "success",
  "error": null
}
```

### `POST /serper`
Google-compatible search transformation.
- **Model**: `SearchRequest`
```json
{
  "q": "best coffee in NYC",
  "num": 10
}
```
- **Response**: `SearchResponse`
```json
{
  "searchParameters": { "q": "...", "type": "search", "engine": "google" },
  "organic": [
    { "title": "Example", "link": "https://example.com", "snippet": "...", "position": 1 }
  ]
}
```

---

## 2. Stateful Interactive Sessions

Long-running sessions managed via WebSockets and JSON DSL.

### `POST /sessions`
Initializes a persistent browser actor.
- **Response**:
```json
{
  "session_id": "uuid-v4",
  "status": "active"
}
```

### `DELETE /sessions/{session_id}`
Terminates a persistent browser actor manually.
- **Response**:
```json
{
  "status": "success",
  "message": "Session uuid-v4 termination signal sent"
}
```

### `POST /sessions/{session_id}/command`
Send a single DSL command to an active session and receive the result synchronously.

Recommended for **MCP / programmatic clients** that cannot hold a persistent WebSocket connection. Internally, the server publishes the command to the same Redis `cmd:{session_id}` channel as the WebSocket handler, then waits (up to 60 s) for the result on `res:{session_id}`.

- **Request**: `CommandRequest`
```json
{
  "type": "goto",
  "params": { "url": "https://news.ycombinator.com" }
}
```
- **Response**: the action result object, e.g.
```json
{ "status": "success", "message": "Navigated to https://news.ycombinator.com" }
```
- **Error responses**:
  - `504 Gateway Timeout` — actor did not respond within 60 s (session may be expired)
  - `422 Unprocessable Entity` — malformed request body

### `WS /ws/{session_id}`
WebSocket connection for sending DSL commands. Recommended for **interactive / streaming clients** (browser frontends, `test_ws.py`, long-running automation scripts) that need bi-directional, low-latency communication and may send many commands over a single connection.

---

## 3. DSL Command Interactions

Commands are sent either over WebSocket or via `POST /sessions/{session_id}/command` in the format:
`{"type": "<command>", "params": { ... }}`

### `goto`
Navigates the current session to a new URL.
```json
{
  "type": "goto",
  "params": {
    "url": "https://news.ycombinator.com"
  }
}
```

### `scroll`
Scrolls the active page.
```json
{
  "type": "scroll",
  "params": {
    "direction": "down",
    "amount": 500
  }
}
```

### `click_coord`
Performs a mouse click at relative coordinates (0.0 to 1.0).
```json
{
  "type": "click_coord",
  "params": {
    "x": 0.5,
    "y": 0.2
  }
}
```

### `type`
Fills a text input field identified by a CSS selector.
```json
{
  "type": "type",
  "params": {
    "selector": "input[name='q']",
    "text": "Taskiq automation"
  }
}
```

### `screenshot`
Captures a base64-encoded screenshot of the current viewport.
```json
{
  "type": "screenshot",
  "params": {}
}
```

---

## 4. AI-Enhanced Interactions (Planned)

### `click_omni`
Clicks an element based on its visual description using Omni-Parser analysis.
```json
{
  "type": "click_omni",
  "params": {
    "element_description": "The big red 'Login' button"
  }
}
```

### `extract_jina`
Extracts structured data from the current page using Jina Reader LM.
```json
{
  "type": "extract_jina",
  "params": {
    "extraction_schema": {
      "title": "string",
      "price": "number"
    }
  }
}
```
