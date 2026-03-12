# STRUCTURE.md - Архитектура проекта

## Обзор

Scraper OS - умный скрапинг-API с LLM-оркестрацией, разделённый на два контура:

1. **Stateless Pool** - быстрые атомарные задачи (скрапинг, поиск)
2. **Stateful Actors** - долгоживущие интерактивные сессии

---

## Структура проекта

```
scraper_os/
├── api/                          # Presentation Layer
│   ├── routers/
│   │   ├── stateless.py          # REST: /scraper, /serper
│   │   └── sessions.py           # REST + WS: /sessions, /ws/{id}
│   ├── websockets/
│   │   └── manager.py            # WebSocket ↔ Redis транслятор
│   ├── main.py                   # FastAPI приложение
│   └── doc.md
│
├── domain/                       # Domain Layer
│   ├── models/
│   │   ├── requests.py           # Pydantic модели
│   │   └── dsl.py                # DSL параметры
│   ├── registry/
│   │   └── __init__.py           # Action Registry
│   └── doc.md
│
├── infrastructure/               # Infrastructure Layer
│   ├── browser/
│   │   ├── pool_manager.py       # Синглтон для Stateless
│   │   └── session_manager.py    # Индивидуальный для сессий
│   ├── llm/
│   │   ├── facade.py             # LLM Facade
│   │   ├── openai_client.py      # OpenAI клиент
│   │   └── jina_client.py        # Jina Reader клиент
│   ├── queue/
│   │   ├── broker.py             # Taskiq + Redis
│   │   ├── pool_workers.py       # Воркеры Scraper/Serper
│   │   └── actor_workers.py      # Actor для сессий
│   └── doc.md
│
├── actions/                      # Command Implementations
│   ├── base.py                   # BaseAction
│   ├── navigation.py             # GoTo, Click, Scroll...
│   ├── extraction.py             # Screenshot, Extract, OmniClick
│   └── doc.md
│
├── core/
│   ├── config.py                 # Pydantic Settings
│   └── doc.md
│
├── tests/                        # Тесты
├── requirements.txt
├── docker-compose.yml
├── README.md
├── ENDPOINTS.md
└── STRUCTURE.md
```

---

## Архитектурные паттерны

### 1. Command Pattern (Action Registry)

Все действия реализуют интерфейс `BaseAction` и регистрируются в реестре:

```python
@ActionRegistry.register("go_to")
class GoToAction(BaseAction):
    async def execute(self, page, params, llm_facade):
        ...
```

### 2. Singleton (BrowserPoolManager)

Глобальный браузер для Stateless задач:

```python
class BrowserPoolManager:
    _browser: Browser = None  # Один на все воркеры
```

### 3. Actor Model (run_stateful_session)

Каждая сессия - отдельный актор с собственным браузером.

### 4. Facade (LLMFacade)

Единый интерфейс для всех AI операций.

---

## Поток данных

### Stateless (REST)

```
Client → FastAPI → Taskiq → BrowserPool → Target
                    ↓
                Redis Queue
                    ↓
              Worker Process
                    ↓
Client ← FastAPI ← Result
```

### Stateful (WebSocket)

```
Client → WebSocket → Redis Pub/Sub (cmd:{id})
                          ↓
                    Actor Worker
                          ↓
                    Browser (session)
                          ↓
                    Redis Pub/Sub (res:{id})
                          ↓
Client ← WebSocket ← Result
```

---

## Диаграммы

### Sequence Diagram: Stateful Session

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant Redis as Redis
    participant Actor as Taskiq Actor
    participant PW as Playwright

    C->>API: POST /sessions
    API->>Redis: Enqueue run_stateful_session
    Actor->>PW: Launch Browser
    Actor->>Redis: SUBSCRIBE cmd:{id}
    API-->>C: session_id

    C->>API: WS /ws/{id}
    API->>Redis: SUBSCRIBE res:{id}

    C->>API: WS: {"action": "go_to"...}
    API->>Redis: PUBLISH cmd:{id}
    Redis->>Actor: Message
    Actor->>PW: page.goto()
    Actor->>Redis: PUBLISH res:{id}
    Redis->>API: Message
    API-->>C: WS: {"success": true...}
```

---

## Конфигурация

### Переменные окружения (.env)

```bash
# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Jina
JINA_API_KEY=...

# Таймауты
SESSION_TIMEOUT_SECONDS=300
REQUEST_TIMEOUT_SECONDS=30

# Прокси сервера
SERPER_PROXIES=["http://proxy1:8080", "socks5://proxy2:1080"]
SCRAPER_PROXIES=["http://proxy1:8080"]
```

---

## Запуск

### 1. Через Docker Compose

```bash
docker-compose up -d
```

### 2. Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt
playwright install chromium

# Запуск Redis
docker run -d -p 6379:6379 redis:7-alpine

# Запуск API
uvicorn scraper_os.api.main:app --reload

# Запуск воркера
taskiq worker scraper_os.infrastructure.queue.broker:broker
```

---

## Тестирование

```bash
pytest tests/ -v
```
