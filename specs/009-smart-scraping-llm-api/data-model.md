# Data Model: Smart Scraping API

## Entities

### 1. ScrapeTask (Stateless)
Represents a single atomic request to fetch or search data.
- **id**: UUID
- **url**: String (target URL or Search Query)
- **type**: Enum (SCRAPE, SEARCH)
- **proxy**: String (Optional override)
- **status**: Enum (PENDING, SUCCESS, FAILED)
- **content**: String (HTML or JSON Search results)
- **error**: String (Optional error message)

### 2. InteractiveSession (Stateful)
Represents a long-running browser session.
- **id**: UUID/SessionID
- **config**: SessionConfig (headless, proxy, user_agent, viewport)
- **status**: Enum (STARTING, ACTIVE, TIMED_OUT, CLOSED)
- **last_active**: Timestamp (for inactivity cleanup)
- **browser_process_id**: Integer (Taskiq Task ID)

### 3. Command (DSL)
A discrete action to be performed in a session.
- **type**: Enum (GOTO, CLICK_COORD, CLICK_OMNI, TYPE, SCROLL, SCREENSHOT, EXTRACT_JINA)
- **params**: JSON (e.g., `{x: 10, y: 20}` or `{text: "search query"}`)
- **result**: JSON (Action-specific output)

## State Transitions

### Interactive Session Lifecycle:
1. **INITIATED**: Client calls `POST /sessions`.
2. **ACTIVE**: Taskiq Actor starts, browser launched, WS connected.
3. **WAITING**: Idle between commands.
4. **CLOSED**: Explicitly closed by client or process finish.
5. **TIMED_OUT**: Automatic transition if `now - last_active > 10m`.

## Validation Rules
- **URL**: Must be valid HTTP/HTTPS.
- **Coordinates**: Must be normalized (0.0 - 1.0) or valid integers within viewport.
- **API Key**: Must match environment `API_KEY`.
