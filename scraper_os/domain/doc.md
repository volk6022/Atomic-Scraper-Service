# Domain Layer

Доменная логика и модели.

## Структура
- `models/` - Pydantic модели данных
- `registry/` - Action Registry (Command Pattern)

## Ответственность
- Определение моделей данных
- Регистрация и исполнение команд через ActionRegistry

## Зависимости
- Pydantic для валидации данных
- BaseAction из модуля actions
