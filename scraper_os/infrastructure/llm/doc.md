# LLM Module

Интеграция с AI сервисами.

## Структура
- `facade.py` - Единый фасад для всех LLM операций
- `openai_client.py` - Клиент для OpenAI API
- `jina_client.py` - Клиент для Jina Reader

## Использование
```python
from infrastructure.llm import LLMFacade

facade = LLMFacade()

# Получить markdown из HTML
markdown = await facade.get_jina_markdown(html)

# Получить координаты кнопки на скриншоте
coords = await facade.get_omni_coordinates(base64_image, "Login button")

# Принять решение о следующем действии
action = await facade.decide_next_action(dom_tree, "Find contact page")
```
