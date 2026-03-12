"""
Base Action - абстрактный базовый класс для всех действий.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from playwright.async_api import Page


class BaseAction(ABC):
    """
    Базовый класс для всех действий (Command Pattern).
    
    Каждое действие должно реализовать метод execute().
    """
    
    @abstractmethod
    async def execute(
        self,
        page: Page,
        params: Dict[str, Any],
        llm_facade: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Выполнить действие.
        
        Args:
            page: Playwright Page объект
            params: Параметры действия (валидированы через Pydantic)
            llm_facade: LLMFacade для AI действий (опционально)
        
        Returns:
            Dict с результатом выполнения, например:
            {"success": True, "data": {...}, "error": None}
        """
        pass
    
    async def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Опциональная валидация параметров.
        По умолчанию всегда возвращает True.
        """
        return True
