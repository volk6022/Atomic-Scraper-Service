# Domain Models

Модели данных предметной области.

## Структура
- `requests.py` - Pydantic модели для входящих запросов и ответов
- `dsl.py` - Модели параметров для DSL команд

## Основные модели

### SessionConfig
Конфигурация Stateful сессии (прокси, user agent, размер окна).

### CommandPayload
Команда для выполнения в сессии (action + params).

### ActionResult
Универсальный результат выполнения действия.
