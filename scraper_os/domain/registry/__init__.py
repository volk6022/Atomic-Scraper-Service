"""
Action Registry - Паттерн Реестр для регистрации и выполнения действий.
"""
from typing import Dict, Type, Optional, Any
from actions.base import BaseAction


class ActionRegistry:
    """
    Реестр действий (Command Pattern).
    Регистрирует действия по имени и предоставляет доступ к ним.
    """
    
    _actions: Dict[str, Type[BaseAction]] = {}
    
    @classmethod
    def register(cls, name: str) -> callable:
        """
        Декоратор для регистрации действия.
        
        Использование:
            @ActionRegistry.register("go_to")
            class GoToAction(BaseAction):
                ...
        """
        def decorator(action_class: Type[BaseAction]) -> Type[BaseAction]:
            cls._actions[name] = action_class
            return action_class
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseAction]]:
        """Получить класс действия по имени"""
        return cls._actions.get(name)
    
    @classmethod
    def create(cls, name: str) -> Optional[BaseAction]:
        """Создать экземпляр действия по имени"""
        action_class = cls.get(name)
        if action_class:
            return action_class()
        return None
    
    @classmethod
    def list_actions(cls) -> list[str]:
        """Вернуть список зарегистрированных действий"""
        return list(cls._actions.keys())
    
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Проверить, зарегистрировано ли действие"""
        return name in cls._actions


# Глобальный экземпляр реестра
registry = ActionRegistry()
