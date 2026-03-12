# Domain Registry

Паттерн Реестр для регистрации действий (Command Pattern).

## Использование

### Регистрация действия
```python
from domain.registry import ActionRegistry
from actions.base import BaseAction

@ActionRegistry.register("my_action")
class MyAction(BaseAction):
    async def execute(self, page, params, llm_facade):
        # логика действия
        return {"result": "success"}
```

### Получение действия
```python
from domain.registry import registry

action = registry.create("my_action")
if action:
    result = await action.execute(page, params, llm_facade)
```

### Список всех действий
```python
actions = registry.list_actions()
```
