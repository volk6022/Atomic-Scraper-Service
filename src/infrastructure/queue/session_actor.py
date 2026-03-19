from typing import Any, Dict
from src.infrastructure.browser.pool_manager import pool_manager
from src.domain.registry.action_registry import action_registry
from src.infrastructure.queue.broker import broker


class SessionActor:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.context = None
        self.page = None

    async def start(self):
        self.context = await pool_manager.create_context()
        self.page = await self.context.new_page()

    async def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        action_type = command.get("type")
        params = command.get("params", {})
        action_func = action_registry.get_action(action_type)
        if action_func:
            return await action_func(self.page, params)
        return {"status": "error", "message": f"Unknown action: {action_type}"}

    async def stop(self):
        if self.context:
            await self.context.close()
