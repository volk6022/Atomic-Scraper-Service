# API WebSockets (src/api/websockets/)

## Files analyzed
- `src/api/websockets/__init__.py` — package marker (пусто).
- `src/api/websockets/handler.py` — FastAPI WebSocket endpoint `/ws/{session_id}`; принимает DSL-команды от клиента, публикует их в Redis на канал `cmd:{session_id}` и в фоне читает `res:{session_id}`, отправляя результаты обратно по WebSocket.
- `src/api/websockets/manager.py` — singleton `ConnectionManager` (имя инстанса — `manager`), обёртка над `redis.asyncio` для publish/subscribe с маппингом ошибок в доменное `RedisUnavailableError`.

## Purpose & responsibilities
Слайс реализует bi-directional bridge между клиентом WebSocket и backend `session_actor` (Taskiq), который держит Playwright-страницу. WebSocket не вызывает actor напрямую — вся координация идёт через два Redis pub/sub канала на сессию (`cmd:{session_id}` и `res:{session_id}`). Это позволяет actor'у работать в отдельном воркере, а WS-эндпоинту — оставаться тонким релеем JSON-сообщений в обе стороны.

## Key classes / functions
- `manager.py::ConnectionManager`
  - `redis` (property) — ленивый `redis.asyncio.Redis` клиент, поднимаемый из `settings`.
  - `async publish_command(session_id: str, command: dict) -> None` — публикует JSON-сериализованную команду в `cmd:{session_id}`. На `ConnectionError|TimeoutError|RedisError` поднимает `RedisUnavailableError("Command publishing temporarily unavailable", {"reason": str(e)})`.
  - `async subscribe_results(session_id: str) -> PubSub` — создаёт PubSub и подписывается на `res:{session_id}`. Тот же error-mapping.
  - Экспортируемый singleton `manager = ConnectionManager()`.
- `handler.py::websocket_endpoint(websocket: WebSocket, session_id: str)` — роутер: `@router.websocket("/ws/{session_id}")`.
- `handler.py::listen_to_redis()` — inner-функция, оборачиваемая в `asyncio.create_task(...)`. Background-task на каждое соединение: `async for message in pubsub.listen()` → фильтр `type == "message"` → `message["data"].decode()` → `await websocket.send_text(...)`.

## Data flow within slice
1. Клиент открывает `WS /ws/{session_id}` (session_id предварительно получен через `POST /sessions`).
2. Хендлер вызывает `websocket.accept()` и `manager.subscribe_results(session_id)` → получает `PubSub`, подписанный на `res:{session_id}`.
3. Запускается фоновая корутина `listen_to_redis()` (через `asyncio.create_task`), которая в цикле читает сообщения из `res:{session_id}` и форвардит их клиенту как `send_text`.
4. Главный цикл хендлера: `data = await websocket.receive_text()` → `command = json.loads(data)` → `await manager.publish_command(session_id, command)` → команда уходит в `cmd:{session_id}`.
5. Внешний `session_actor` (Taskiq), подписанный на `cmd:{session_id}`, выполняет действие на Playwright и публикует результат в `res:{session_id}`.
6. Результат подхватывается background-task'ом п. 3 и уходит клиенту.
7. На `WebSocketDisconnect`: вызывается `pubsub.unsubscribe(f"res:{session_id}")`. Background-task явно не отменяется (полагается на завершение pubsub-итератора).

Каналы Redis:
- `cmd:{session_id}` — команды client → actor.
- `res:{session_id}` — результаты actor → client.
(Тот же `cmd:{session_id}` использует и REST `POST /sessions/{session_id}/command`, согласно `web_interactions.md` — это альтернативный путь для MCP/HTTP-клиентов.)

## Mermaid diagram(s)
```mermaid
sequenceDiagram
    participant Client
    participant WS as WS Handler (/ws/{sid})
    participant Mgr as ConnectionManager
    participant Redis
    participant Actor as session_actor (Taskiq)

    Client->>WS: WebSocket connect /ws/{sid}
    WS->>Mgr: subscribe_results(sid)
    Mgr->>Redis: SUBSCRIBE res:{sid}
    WS-->>WS: asyncio.create_task(listen_to_redis)

    loop until disconnect
        Client->>WS: send_text(JSON command)
        WS->>WS: json.loads(data)
        WS->>Mgr: publish_command(sid, command)
        Mgr->>Redis: PUBLISH cmd:{sid} <json>
        Actor->>Redis: (subscriber) cmd:{sid}
        Actor->>Actor: execute on Playwright
        Actor->>Redis: PUBLISH res:{sid} <json>
        Redis-->>WS: message on res:{sid}
        WS->>Client: send_text(result)
    end

    Client--xWS: WebSocketDisconnect
    WS->>Redis: UNSUBSCRIBE res:{sid}
    Note over WS,Actor: TERMINATE actor НЕ шлётся;<br/>сессия завершается по TTL или DELETE /sessions/{sid}
```

## External dependencies
- `redis.asyncio.Redis` — через `manager.redis` (URL/настройки из `src.core.config.settings`).
- Доменная ошибка `src.domain.models.errors.RedisUnavailableError`.
- `fastapi.{APIRouter, WebSocket, WebSocketDisconnect}` — транспорт.
- Косвенно: `session_actor` (Taskiq) — подписчик `cmd:{session_id}`, паблишер `res:{session_id}`; `pool_manager` — поднимает actor в `POST /sessions` (создаёт сессию до того, как клиент откроет WS). Сам слайс к ним не импортируется.

## Tests covering this slice
Поиск по `tests/**/*ws*.py` и `tests/**/*websocket*.py` дал:
- `tests/unit/test_stealth_browser.py` — не относится к WS.
- `tests/contract/test_yandex_maps_reviews_api.py` — не относится к WS.

Явных unit/contract тестов на WebSocket handler в репозитории нет. Существует упомянутый в `web_interactions.md` интерактивный скрипт `test_ws.py` (вне `tests/`), но это не pytest-тест.

## Open questions / smells
- **Heartbeat/keepalive отсутствует.** Нет ни custom ping/pong, ни конфигурации FastAPI/Starlette ping interval — за долгоживущими соединениями через прокси/LB могут срываться idle-таймауты.
- **Background-task не отменяется явно** при `WebSocketDisconnect`. Полагается на естественное завершение `pubsub.listen()`; при определённых ошибках Redis это может оставить «висячую» корутину.
- **PubSub не закрывается** (`await pubsub.close()`/`reset()` не вызывается) — только `unsubscribe`. Возможна утечка соединений Redis при массовых дисконнектах.
- **Отсутствует общий `try/except/finally`** для не-`WebSocketDisconnect` исключений (RedisUnavailableError, JSONDecodeError на `json.loads(data)`, прочие). Клиент при битом JSON получит закрытие WS без структурированного error-сообщения.
- **TERMINATE в actor не шлётся при disconnect.** Сессия живёт до TTL или явного `DELETE /sessions/{sid}` — потенциальная утечка Playwright-контекстов, если клиент просто закрыл вкладку.
- **Расхождение со спекой `contracts/websocket.md`:** контракт декларирует поля `action` и `params` для входящих сообщений и `{status, action, data}` для исходящих. Handler же принимает произвольный JSON (`command = json.loads(data)`) и форвардит сырые строки из Redis — никакой валидации Pydantic-схемой нет. `web_interactions.md` (CommandRequest) использует ключ `type`, а спека — `action`; согласованности нет, handler пропускает оба варианта вслепую.
- **Нет ограничения размера сообщения** и rate-limit на `receive_text` — потенциальный DoS-вектор.
- **`session_id` не валидируется** на существование/принадлежность клиенту: любой может подключиться к `/ws/{любой-uuid}` и снифать `res:{sid}` чужой сессии.
