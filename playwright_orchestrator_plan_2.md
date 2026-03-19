# Архитектурный план: Умный Скрапинг-API с LLM-оркестрацией

## 1. Уточненное архитектурное видение

Система строго разделена на два изолированных контура выполнения:

### Контур А: Stateless Pool (Serper & Scraper)
*   **Назначение:** Быстрые атомарные задачи. Вытащить HTML, сделать поиск.
*   **Жизненный цикл:** При старте воркера (событие `startup` в Taskiq) запускается один глобальный инстанс Playwright. Он не закрывается никогда (до остановки самого воркера).
*   **Обработка запроса:** Прилетает задача -> создается новый `browser.new_context(proxy=...)` -> выполняется скрапинг -> `context.close()`.
*   **Прокси:** Берутся сервером из локального конфигурационного файла (Round-robin выборка из пула HTTP/SOCKS5).
*   **Взаимодействие:** Строго через REST API (FastAPI -> Taskiq -> FastAPI -> Client).

### Контур Б: Stateful Actors (Интерактивные сессии)
*   **Назначение:** Долгоживущие сессии для сложных сценариев (кликанье кнопок через LLM, Omni-Parser, навигация).
*   **Жизненный цикл:** Запуск отдельного воркера-актора (Actor Model). Актор поднимает *свой собственный* браузер.
*   **Взаимодействие:** Двустороннее. Клиент шлет команды по WebSocket, сервер транслирует их через Redis Pub/Sub в Актора. Результаты (включая скриншоты в `base64`) летят обратно.
*   **Устойчивость (Отключение и Таймауты):** Актор отслеживает время последней полученной команды. Если клиент отвалился от WebSocket, сессия на сервере "зависает" и ждет. Если `time_now - last_command_time > TIMEOUT` (из конфига), Актор **безусловно** убивает браузер и завершает процесс, чтобы освободить ресурсы. Прокси задаются клиентом.

---

## 2. Стек технологий и Зависимости

```text
# requirements.txt
fastapi==0.110.0
uvicorn[standard]==0.28.0
websockets==12.0
pydantic==2.6.4
pydantic-settings==2.2.1
playwright==1.42.0
taskiq==0.11.0
taskiq-fastapi==0.3.0
taskiq-redis==0.5.1
redis==5.0.3
openai==1.14.2        # Для совместимых API (LLM, Omni, Jina)
httpx==0.27.0         # Для прямых REST вызовов
pytest==8.1.1
pytest-asyncio==0.23.5
```

---

## 3. Структура файловой системы (Clean Architecture)

```text
scraper_os/
├── api/                           #[Presentation] HTTP и WebSockets
│   ├── routers/
│   │   ├── sessions.py            # Управление Stateful сессиями
│   │   └── stateless.py           # Serper & Scraper эндпоинты
│   ├── websockets/
│   │   └── manager.py             # WS транслятор в Redis
│   └── doc.md
├── domain/                        # [Domain] Модели и абстракции
│   ├── models/
│   │   ├── requests.py            # Pydantic модели входящих данных
│   │   └── dsl.py                 # Модели CommandPayload (JSON команды)
│   ├── registry/                  # Action Registry (Паттерн Реестр)
│   └── doc.md
├── infrastructure/                #[Infrastructure] Внешние взаимодействия
│   ├── browser/
│   │   ├── pool_manager.py        # Глобальный браузер для Stateless задач
│   │   └── session_manager.py     # Изолированный браузер для Stateful сессий
│   ├── external_api/
│   │   ├── facade.py              # LLMFacade (Единая точка входа)
│   │   ├── openai_client.py
│   │   └── jina_client.py
│   ├── queue/
│   │   ├── broker.py              # Настройка Taskiq + Redis
│   │   ├── pool_workers.py        # Воркеры Scraper/Serper
│   │   └── actor_workers.py       # Воркер жизненного цикла сессии
│   └── doc.md
├── actions/                       # Реализации команд (DSL)
│   ├── base.py                    # Абстрактный BaseAction
│   ├── navigation.py
│   ├── extraction.py
│   └── doc.md
├── core/
│   ├── config.py                  # Pydantic Settings (Таймауты, пулы прокси)
│   └── doc.md
├── tests/
├── README.md
├── ENDPOINTS.md
└── STRUCTURE.md
```

---

## 4. Архитектурные диаграммы (Mermaid)

### 4.1. Sequence Diagram: Stateful Actor & Жизнестойкость (Отключение + Таймаут)

Отражает логику работы таймаута при обрыве связи WebSocket.

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant FastAPI as FastAPI (REST/WS)
    participant Redis as Redis (Pub/Sub)
    participant Taskiq as Taskiq Worker (Actor)
    participant PW as Playwright
    participant LLM as Omni-Parser / Jina

    Client->>FastAPI: POST /sessions (config: proxy, headless)
    FastAPI->>Taskiq: Enqueue `run_stateful_actor(session_id)`
    Taskiq->>PW: Запуск Browser Context
    Taskiq->>Redis: Subscribe: `cmd:{session_id}`
    FastAPI-->>Client: 200 OK: session_id

    Client->>FastAPI: Connect WS: /ws/{session_id}
    FastAPI->>Redis: Subscribe: `result:{session_id}`
    
    Client->>FastAPI: WS JSON: {"action": "omni_click", "target": "Login"}
    FastAPI->>Redis: Publish to `cmd:{session_id}`
    Redis-->>Taskiq: Receive command
    
    Taskiq->>PW: page.screenshot(base64)
    PW-->>Taskiq: base64 image
    
    Taskiq->>LLM: POST (base64 image + prompt: "Find Login")
    LLM-->>Taskiq: JSON с координатами (x, y)
    
    Taskiq->>PW: page.mouse.click(x, y)
    PW-->>Taskiq: Success
    
    Taskiq->>Redis: Publish to `result:{session_id}`: {"status": "ok"}
    Redis-->>FastAPI: Receive result
    FastAPI-->>Client: WS JSON: {"status": "ok"}

    Note over Client, FastAPI: Клиент внезапно отключается (Network Error)
    Client--xFastAPI: Connection Dropped
    FastAPI->>FastAPI: Clean WS connections
    
    Note over Taskiq: Actor продолжает крутить цикл <br/> await asyncio.wait_for(..., timeout=1.0)
    
    loop Heartbeat Check
        Taskiq->>Taskiq: Check: (now - last_active_time) > config.TIMEOUT
    end
    
    Note over Taskiq, PW: Прошло N минут без команд (Таймаут!)
    Taskiq->>PW: Force Browser.close()
    Taskiq->>Taskiq: Exit Taskiq Worker Process
```

### 4.2. Data Flow Diagram

Схема иллюстрирует разделение ресурсов между Stateless и Stateful.

```mermaid
flowchart TD
    subgraph Clients
        C1[Client 1: REST]
        C2[Client 2: WebSocket]
    end

    subgraph Configs
        SConf[Server Config: Proxy Pool]
        CConf[Client Config: Proxy & UA]
    end

    subgraph API
        REST[FastAPI REST]
        WS[FastAPI WS]
    end

    subgraph Redis
        Q[(Taskiq Queue)]
        PS((Pub/Sub Channels))
    end

    subgraph Stateless Workers Pool
        W1[Worker Process 1]
        B1{{Playwright Instance 1 <br/>NEVER CLOSES}}
        W1 -- Uses --> B1
        W1 -- Reads --> SConf
    end

    subgraph Stateful Actors
        W2[Actor Process A]
        B2{{Playwright Instance A <br/>Closes on Timeout}}
        W2 -- Owns --> B2
        W2 -- Reads --> CConf
    end

    C1 -->|GET /scrape| REST
    REST -->|Push Job| Q
    Q -->|Consume| W1
    W1 -->|Creates Context| B1

    C2 <-->|WS| WS
    WS -->|Commands| PS
    PS -->|Subscribed| W2
    W2 -->|Executes| B2
```

### 4.3. Асинхронность и Конкурентность (Потоки и Блокировки)

Показывает, где используется `asyncio`, а где процессы `Taskiq`.

```mermaid
gantt
    title Async Execution Flow & Worker Separation
    dateFormat  s
    axisFormat %S

    section FastAPI Event Loop
    REST Scrape req       :active, a1, 0, 1s
    WS Session stream     :active, a2, 0, 8s
    note over a1,a2 : FastAPI только перекладывает JSON в Redis. 0% загрузки CPU.
    
    section Stateless Worker Process 1
    Worker Boot + Browser :crit, b1, 0, 2s
    Create Incognito Context:active, b2, 2, 1s
    Scrape Target 1       :active, b3, 3, 2s
    Context.close()       :b4, 5, 1s
    Create Incognito Context:active, b5, 6, 1s
    Scrape Target 2       :active, b6, 7, 2s
    note over b1, b6: Процесс браузера не закрывается, контексты пересоздаются.
        
    section Stateful Actor (Process 2)
    LLM Omni-Parser Call (Network I/O):active, c1, 1, 3s
    Playwright Mouse Move (I/O)       :active, c2, 4, 1s
    Base64 Encode (CPU Bound!)        :crit, c3, 5, 1s
    Wait in Redis PubSub (Sleep)      :c4, 6, 2s
```

---

## 5. Модель данных и описание классов

### 5.1. Конфигурации и Модели (Pydantic)

```python
# domain/models/requests.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SessionConfig(BaseModel):
    headless: bool = True
    proxy: Optional[str] = None # Формат: socks5://user:pass@host:port
    user_agent: Optional[str] = None
    window_size: Dict[str, int] = {"width": 1920, "height": 1080}

class CommandPayload(BaseModel):
    action: str = Field(..., description="Имя действия из ActionRegistry")
    params: Dict[str, Any] = Field(default_factory=dict)
```

### 5.2. Инфраструктура: Browser Pool (Синглтон для Stateless)

Здесь мы реализуем паттерн, при котором Playwright живет столько же, сколько процесс Taskiq.

```python
# infrastructure/browser/pool_manager.py
from playwright.async_api import async_playwright, Browser, BrowserContext

class BrowserPoolManager:
    _playwright = None
    _browser: Browser = None

    @classmethod
    async def start(cls):
        """Вызывается при старте воркера Taskiq (@broker.on_event('startup'))"""
        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch(headless=True)

    @classmethod
    async def stop(cls):
        """Вызывается при остановке воркера (@broker.on_event('shutdown'))"""
        if cls._browser:
            await cls._browser.close()
        if cls._playwright:
            await cls._playwright.stop()

    @classmethod
    async def new_context(cls, proxy: str = None) -> BrowserContext:
        """Создает быстрый изолированный контекст для Scraper/Serper"""
        proxy_settings = {"server": proxy} if proxy else None
        return await cls._browser.new_context(proxy=proxy_settings)
```

### 5.3. Ядро: Actor и контроль таймаута

```python
# infrastructure/queue/actor_workers.py
import asyncio
import time
from core.config import settings

@broker.task
async def run_stateful_session(session_id: str, config: SessionConfig):
    last_active = time.time()
    
    # 1. Запуск изолированного браузера для актора
    browser_manager = SessionBrowserManager(config)
    page = await browser_manager.init()
    
    # 2. Подписка на Redis
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"cmd:{session_id}")
    
    try:
        while True:
            # Проверка таймаута бездействия
            if time.time() - last_active > settings.SESSION_TIMEOUT_SECONDS:
                logger.warning(f"Session {session_id} timeout. Killing.")
                break # Выход из цикла закроет браузер в блок finally

            # Асинхронное ожидание сообщения (1 секунда, чтобы цикл крутился и чекал таймаут)
            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0)
                if message:
                    last_active = time.time()
                    payload = CommandPayload.parse_raw(message['data'])
                    
                    # Исполнение через Паттерн Registry
                    action = registry.get(payload.action)()
                    result = await action.execute(page, payload.params, llm_facade)
                    
                    await redis_client.publish(f"res:{session_id}", result.json())
            except asyncio.TimeoutError:
                continue # Просто тик цикла
    finally:
        await browser_manager.close()
```

### 5.4. Паттерн Фасад для ИИ (LLMFacade)

```python
# infrastructure/external_api/facade.py
class LLMFacade:
    def __init__(self):
        # Клиенты инициализируются внутри (Httpx / OpenAI)
        pass

    async def get_jina_markdown(self, html: str, extract_schema: dict = None) -> dict:
        """Обращение к Jina ReaderV2 Hf Endpoint (как указано в ТЗ)"""
        pass

    async def get_omni_coordinates(self, base64_image: str, target: str) -> dict:
        """Вызов Omni-Parser для поиска кнопки на скриншоте"""
        pass

    async def decide_next_action(self, dom_tree: str, objective: str) -> dict:
        """Вызов OpenAI Structured Output: 'Какую кнопку нажать дальше?'"""
        pass
```

---

## 6. Подробный пошаговый план реализации (Roadmap)

Проект сложный, поэтому разбиваем его на управляемые спринты. Мы будем идти от инфраструктуры ядра к API, чтобы тестировать функционал инкрементально.

### Спринт 1: Базовая инфраструктура и Модели (Дни 1-2)
1. Инициализация проекта: создание виртуального окружения, установка зависимостей из `requirements.txt`.
2. Создание Pydantic настроек (`core/config.py`). Настройка пула прокси для сервера (`SERPER_PROXIES = [...]`) и таймаутов.
3. Написание слоя Domain: `SessionConfig`, `CommandPayload`.
4. Реализация паттерна Реестр (`domain/registry/`). Создание базового класса `BaseAction`.
5. Разворачивание Redis через `docker-compose.yml`.

### Спринт 2: Playwright и Taskiq (Дни 3-4)
1. Настройка брокера Taskiq (`infrastructure/queue/broker.py`) с бекендом Redis.
2. Реализация **Stateless Pool**:
    * Класс `BrowserPoolManager` с хуками на старт/стоп воркера.
    * Задача Taskiq `scrape_task`, которая берет контекст, настраивает прокси из пула, скачивает HTML.
    * Задача Taskiq `serper_task` для поисковых запросов.
3. Реализация **Stateful Actor**:
    * Менеджер индивидуального инстанса браузера `SessionBrowserManager`.
    * Актор `run_stateful_session` с циклом ожидания, Redis Pub/Sub и **логикой жесткого таймаута**, как мы обсудили.

### Спринт 3: Интеграция LLM / VLM (День 5-6)
1. Реализация `LLMFacade`.
2. Интеграция Jina-ReaderV2: HTTPX запрос к HuggingFace Endpoint с передачей HTML и `structured_output` схемы.
3. Интеграция OpenAI (Structured Output) для принятия решений ("Какую кнопку нажать").
4. Интеграция Omni-Parser (подготовка промптов и передача base64 картинок).

### Спринт 4: Реализация DSL Actions (День 7)
1. Создание конкретных команд в `actions/`:
    * `NavigationActions` (GoTo, ClickCoordinate, Scroll).
    * `ExtractionActions` (GetBase64Screenshot, GetHTML).
    * `AIActions` (OmniClick — связка скриншота, Omni-parser и клика; ExtractWithJina).
2. Покрытие `ActionRegistry` и логики экшенов юнит-тестами с использованием моков Playwright.

### Спринт 5: FastAPI и WebSockets (Дни 8-9)
1. REST Эндпоинты `/scraper` и `/serper`, которые пушат задачи в `scrape_task` и ждут результат (`task.wait_result()`).
2. REST Эндпоинты `/sessions` (создание, где клиентом передаются прокси, и принудительное ручное завершение сессии).
3. WebSocket Manager: эндпоинт `/ws/{session_id}`.
    * При подключении — подписка на канал `res:{id}`.
    * При получении JSON от клиента — пуш в канал `cmd:{id}`.
    * Обработка дисконнектов клиента (без завершения сессии).

### Спринт 6: Документация и Финализация (День 10)
1. Написание `ENDPOINTS.md` с подробнейшими примерами JSON payloads для REST и WS.
2. Написание `STRUCTURE.md` с текстовым дублированием логики и диаграммами Mermaid.
3. Добавление `doc.md` в каждую директорию.
4. Сквозное (E2E) тестирование всей системы. Проверка утечек памяти: убедиться, что таймаут корректно закрывает браузер и освобождает RAM.
