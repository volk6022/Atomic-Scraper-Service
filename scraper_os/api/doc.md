# API Module

Presentation layer - HTTP REST API и WebSocket.

## Структура
- `routers/stateless.py` - REST эндпоинты для Scraper/Serper
- `routers/sessions.py` - REST эндпоинты для управления сессиями
- `websockets/manager.py` - WebSocket менеджер для streaming сессий

## Эндпоинты

### Stateless (REST)
- `POST /scraper` - Скрапинг URL
- `POST /serper` - Поисковый запрос

### Stateful (REST + WS)
- `POST /sessions` - Создать сессию
- `DELETE /sessions/{session_id}` - Завершить сессию
- `GET /sessions/{session_id}/status` - Статус сессии
- `WS /ws/{session_id}` - WebSocket для команд
