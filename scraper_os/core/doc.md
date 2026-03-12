# Core Module

Модуль конфигурации приложения.

## Структура
- `config.py` - Pydantic Settings с настройками прокси, таймаутов, API ключей

## Использование
```python
from core.config import settings

# Доступ к настройкам
proxies = settings.SCRAPER_PROXIES
timeout = settings.SESSION_TIMEOUT_SECONDS
```
