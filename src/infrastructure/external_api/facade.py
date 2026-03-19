from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMFacade(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        pass

    @abstractmethod
    async def extract(self, content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        pass
