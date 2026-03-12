# DSL Actions

Concrete implementations of commands that can be executed on a Playwright page.

## Structure
- `base.py`: Contains `BaseAction` abstract class and common helpers (like `_safe_screenshot`).
- `navigation.py`: Basic navigation actions like `goto`, `click`, and `scroll`.
- `extraction.py`: Content retrieval actions like `get_html` and `screenshot`.
- `ai_actions.py`: High-level AI-powered actions like `omni_click` and `smart_step`.

## Adding New Actions
1. Create a new class in the appropriate file.
2. Inherit from `BaseAction`.
3. Decorate with `@register("your_action_name")`.
4. Implement the `async def execute(...)` method.
