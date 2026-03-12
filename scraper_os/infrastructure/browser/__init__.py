"""Browser module - менеджеры браузеров"""
from .pool_manager import BrowserPoolManager
from .session_manager import SessionBrowserManager

__all__ = ["BrowserPoolManager", "SessionBrowserManager"]
