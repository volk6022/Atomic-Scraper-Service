# Atomic Scraper Service

Умный скрапинг-API с LLM-оркестрацией для автоматизации веб-взаимодействий.

## Особенности

- **Stateless Pool** - Быстрые атомарные задачи (скрапинг HTML, поисковые запросы)
- **Stateful Actors** - Долгоживущие интерактивные сессии с WebSocket
- **LLM Integration** - OpenAI для принятия решений, Jina Reader для Markdown
- **AI Actions** - Omni-Parser для поиска элементов на скриншотах
- **Proxy Support** - Round-robin пул прокси для сервера, клиентские прокси для сессий
- **Timeout Protection** - Автоматическое закрытие неактивных сессий

## Архитектура

Система разделена на два изолированных контура:

### Контур A: Stateless Pool
- Глобальный браузер Playwright на воркер
- Изолированные контексты для каждой задачи
- REST API через Taskiq + Redis

### Контур Б: Stateful Actors
- Отдельный браузер на сессию
- WebSocket + Redis Pub/Sub
- Таймаут бездействия = закрытие

## Быстрый старт

### 1. Клонирование и установка

```bash
cd scraper_os
pip install -r requirements.txt
playwright install chromium
```

### 2. Настройка

Создайте `.env` файл:

```bash
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-your-key
JINA_API_KEY=your-jina-key
SESSION_TIMEOUT_SECONDS=300
```

### 3. Запуск Redis

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### 4. Запуск API

```bash
uvicorn scraper_os.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Запуск воркера

```bash
taskiq worker scraper_os.infrastructure.queue.broker:broker
```

### 6. Проверка

Откройте http://localhost:8000/docs

## Примеры использования

### Stateless скрапинг

```python
import httpx

response = httpx.post("http://localhost:8000/api/v1/scraper", json={
    "url": "https://example.com"
})
html = response.json()["data"]["html"]
```

### Stateful сессия с WebSocket

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
    
    # WebSocket подключение
    async with websockets.connect(f"ws://localhost:8000/api/v1/ws/{session_id}") as ws:
        # Переход на страницу
        await ws.send(json.dumps({
            "action": "go_to",
            "params": {"url": "https://example.com"}
        }))
        print(await ws.recv())
        
        # Скриншот
        await ws.send(json.dumps({
            "action": "screenshot",
            "params": {"full_page": True}
        }))
        result = json.loads(await ws.recv())
        print(f"Screenshot: {len(result['data']['image'])} bytes")

asyncio.run(main())
```

### AI клик (Omni-Parser)

```python
await ws.send(json.dumps({
    "action": "omni_click",
    "params": {"target": "Sign In button"}
}))
```

## Доступные действия

### Навигация
- `go_to` - Перейти на URL
- `click` - Клик по селектору
- `click_coordinate` - Клик по координатам
- `scroll` - Прокрутка
- `type` - Ввод текста
- `press_key` - Нажать клавишу

### Извлечение
- `screenshot` - Скриншот (base64)
- `extract_html` - Извлечь HTML
- `extract_text` - Извлечь текст
- `extract_markdown` - Markdown через Jina
- `omni_click` - AI клик по описанию
- `ai_decide` - AI решение о следующем действии

## Документация

- [ENDPOINTS.md](scraper_os/ENDPOINTS.md) - Полная документация API
- [STRUCTURE.md](scraper_os/STRUCTURE.md) - Архитектура и диаграммы

## Технологический стек

- **FastAPI** - REST API и WebSocket
- **Playwright** - Автоматизация браузера
- **Taskiq** - Очередь задач
- **Redis** - Брокер сообщений + Pub/Sub
- **Pydantic** - Валидация данных
- **OpenAI** - LLM для решений
- **Jina Reader** - HTML → Markdown

## Лицензия

MIT
