# ENDPOINTS.md - Документация API

## Stateless API (REST)

### POST /api/v1/scraper

Скрапинг URL.

**Request:**
```json
{
  "url": "https://example.com",
  "proxy": "http://user:pass@proxy:8080",
  "wait_selector": ".content",
  "wait_timeout": 5000
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "html": "<!DOCTYPE html>...",
    "url": "https://example.com",
    "status": 200
  },
  "error": null
}
```

---

### POST /api/v1/serper

Поисковый запрос.

**Request:**
```json
{
  "query": "python web scraping",
  "num_results": 10,
  "proxy": null
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "title": "Example Title",
        "url": "https://example.com",
        "snippet": "Description text..."
      }
    ],
    "query": "python web scraping"
  },
  "error": null
}
```

---

## Stateful API (REST + WebSocket)

### POST /api/v1/sessions

Создать новую сессию.

**Request:**
```json
{
  "headless": true,
  "proxy": "socks5://user:pass@proxy:1080",
  "user_agent": "Mozilla/5.0...",
  "window_size": {
    "width": 1920,
    "height": 1080
  }
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "starting",
  "message": "Session is starting, connect via WebSocket"
}
```

---

### DELETE /api/v1/sessions/{session_id}

Принудительно завершить сессию.

**Response:**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Session closed"
}
```

---

### GET /api/v1/sessions/{session_id}/status

Получить статус сессии.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "active": true,
  "created_at": 1710000000.0,
  "last_activity": 1710000100.0,
  "proxy": "socks5://...",
  "headless": true,
  "ws_connections": 1
}
```

---

### WebSocket /api/v1/ws/{session_id}

Интерактивное управление сессией.

**Подключение:**
```
ws://localhost:8000/api/v1/ws/{session_id}
```

**Команда (Client → Server):**
```json
{
  "action": "go_to",
  "params": {
    "url": "https://example.com"
  }
}
```

**Ответ (Server → Client):**
```json
{
  "success": true,
  "data": {
    "url": "https://example.com",
    "title": "Example Domain",
    "status": 200
  },
  "error": null
}
```

---

## Доступные действия (Actions)

### Навигация

| Action | Параметры | Описание |
|--------|-----------|----------|
| `go_to` | `url`, `wait_until`, `timeout` | Перейти на URL |
| `click` | `selector`, `timeout` | Клик по элементу |
| `click_coordinate` | `x`, `y` | Клик по координатам |
| `scroll` | `direction`, `amount` | Прокрутка |
| `type` | `selector`, `text`, `delay` | Ввод текста |
| `press_key` | `key` | Нажать клавишу |

### Извлечение

| Action | Параметры | Описание |
|--------|-----------|----------|
| `screenshot` | `full_page`, `quality` | Скриншот (base64) |
| `extract_html` | `selector` | Извлечь HTML |
| `extract_text` | `selector` | Извлечь текст |
| `extract_markdown` | - | Markdown через Jina |
| `omni_click` | `target` | AI клик по описанию |
| `ai_decide` | `objective` | AI решение |

---

## Примеры использования

### Пример 1: Простой скрапинг

```python
import httpx

response = httpx.post("http://localhost:8000/api/v1/scraper", json={
    "url": "https://example.com"
})
print(response.json()["data"]["html"])
```

### Пример 2: Сессия с WebSocket

```python
import asyncio
import websockets
import json

async def main():
    # Создаём сессию
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:8000/api/v1/sessions", json={
            "headless": True
        })
        session_id = resp.json()["session_id"]
    
    # Подключаемся к WebSocket
    async with websockets.connect(f"ws://localhost:8000/api/v1/ws/{session_id}") as ws:
        # Переход на страницу
        await ws.send(json.dumps({
            "action": "go_to",
            "params": {"url": "https://example.com"}
        }))
        
        # Получаем ответ
        response = await ws.recv()
        print(response)
        
        # Скриншот
        await ws.send(json.dumps({
            "action": "screenshot",
            "params": {"full_page": True}
        }))
        
        response = await ws.recv()
        data = json.loads(response)
        print(f"Screenshot: {len(data['data']['image'])} bytes")

asyncio.run(main())
```

### Пример 3: AI клик

```python
# Omni-click через AI
await ws.send(json.dumps({
    "action": "omni_click",
    "params": {"target": "Sign In button"}
}))

response = await ws.recv()
print(response)
```
