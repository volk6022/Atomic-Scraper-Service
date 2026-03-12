# Actions Module

Реализация команд DSL для управления браузером.

## Структура
- `base.py` - Абстрактный базовый класс BaseAction
- `navigation.py` - Действия навигации (GoTo, Click, Scroll, Type)
- `extraction.py` - Действия извлечения (Screenshot, ExtractHTML, OmniClick)

## Регистрация действий
Действия регистрируются через декоратор @ActionRegistry.register("name")

## Пример использования
```python
from domain.registry import registry

action = registry.create("go_to")
result = await action.execute(page, {"url": "https://example.com"})
```
