# WebSocket Protocol Contract

**URL**: `/ws/{session_id}`

## Client -> Server (Commands)
```json
{
  "action": "click_coord",
  "params": {
    "x": 0.5,
    "y": 0.2
  }
}
```

## Server -> Client (Results)
```json
{
  "status": "success",
  "action": "click_coord",
  "data": {}
}
```

## Supported Actions
- `goto`: `{"url": "..."}`
- `click_coord`: `{"x": float, "y": float}`
- `click`: `{"selector": "...", "type": "text|html|attribute"}`
- `fill`: `{"text": "...", "selector": "...", "type": "text|html|attribute"}`
- `extract`: `{"selector": "...", "type": "text|html|attribute", "attribute": "..."}`
- `screenshot`: `{}`
- `screenshot_full`: `{}`
- `click_full_coord`: `{"x": float, "y": float}`
- `fill_full_coord`: `{"x": float, "y": float, "value": "..."}`
- `extract_jina`: `{"schema": {...}}`
