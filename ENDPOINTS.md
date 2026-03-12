# API Endpoints Documentation

## 1. Stateless Pool (Circuit A)

Fast, atomic tasks for one-off scraping and searching. No session state is maintained between requests.

### POST /scraper
Scrape a single URL.

**Payload:**
```json
{
  "url": "https://example.com",
  "wait_for": "h1",
  "extract_text": false,
  "proxy": "socks5://user:pass@host:port" (optional)
}
```

**Response:**
```json
{
  "status": "success",
  "data": "<html>...</html>",
  "metadata": { ... }
}
```

### POST /serper
Simulated search via scraping.

**Payload:**
```json
{
  "query": "playwright python",
  "num_results": 10
}
```

---

## 2. Stateful Sessions (Circuit B)

Long-lived interactive sessions with browser persistence.

### POST /sessions
Initialize a new stateful session.

**Payload:**
```json
{
  "config": {
    "headless": true,
    "proxy": "socks5://user:pass@host:port",
    "user_agent": "Mozilla/5.0...",
    "window_size": {"width": 1920, "height": 1080}
  }
}
```

**Response:**
```json
{
  "session_id": "a1b2c3d4...",
  "status": "active"
}
```

### DELETE /sessions/{session_id}
Gracefully terminate a session and release resources.

---

## 3. WebSocket Session Interface

Connect via `ws://{host}/ws/{session_id}` for real-time control.

### Client -> Server (Command Payload)
```json
{
  "action": "string",
  "params": { ... }
}
```

### Available Actions

| Action | Parameters | Description |
| :--- | :--- | :--- |
| `goto` | `url` (str), `timeout` (int), `wait_until` (str) | Navigate to a URL. |
| `click` | `selector` (str) OR `x`, `y` (int) | Click an element. |
| `scroll` | `direction` ("up", "down", "top", "bottom"), `amount` (int) | Scroll the page. |
| `get_html` | `selector` (str, optional) | Get HTML content of the page or element. |
| `screenshot` | `full_page` (bool) | Take a base64 screenshot. |
| `omni_click` | `target` (str) | Use AI (Omni-Parser) to find and click an element. |
| `jina_extract`| `schema` (dict, optional) | Extract data/Markdown using Jina Reader. |
| `smart_step` | `objective` (str) | Ask LLM for the next recommended action. |
| `exit` | none | Close the session. |

### Server -> Client (Action Result)
```json
{
  "action": "string",
  "status": "ok" | "fail",
  "message": "Error message if failed",
  "data": { ... },
  "screenshot": "base64..." (optional)
}
```
