"""
Domain models - Pydantic модели для входящих данных и команд.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class SessionConfig(BaseModel):
    """
    Конфигурация Stateful сессии.
    Передаётся клиентом при создании сессии.
    """
    headless: bool = True
    proxy: Optional[str] = None  # Формат: socks5://user:pass@host:port или http://...
    user_agent: Optional[str] = None
    window_size: Dict[str, int] = Field(
        default_factory=lambda: {"width": 1920, "height": 1080},
        description="Размер окна браузера"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "headless": True,
                "proxy": "socks5://user:pass@proxy.example.com:1080",
                "user_agent": "Mozilla/5.0...",
                "window_size": {"width": 1920, "height": 1080}
            }
        }


class CommandPayload(BaseModel):
    """
    Команда для выполнения в Stateful сессии.
    Используется в WebSocket и Redis Pub/Sub.
    """
    action: str = Field(..., description="Имя действия из ActionRegistry")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Параметры для действия"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "action": "go_to",
                "params": {"url": "https://example.com"}
            }
        }


class ScraperRequest(BaseModel):
    """
    Запрос на скрапинг (Stateless).
    """
    url: str = Field(..., description="URL для скрапинга")
    proxy: Optional[str] = Field(None, description="Прокси для запроса (опционально)")
    wait_selector: Optional[str] = Field(None, description="CSS селектор для ожидания")
    wait_timeout: int = Field(5000, description="Таймаут ожидания в мс")
    headless: bool = Field(True, description="Headless режим")
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "wait_selector": ".content",
                "wait_timeout": 5000
            }
        }


class SerperRequest(BaseModel):
    """
    Запрос к поисковику Serper (Stateless).
    """
    query: str = Field(..., description="Поисковый запрос")
    num_results: int = Field(10, description="Количество результатов", ge=1, le=100)
    proxy: Optional[str] = Field(None, description="Прокси для запроса")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "python web scraping",
                "num_results": 10
            }
        }


class ActionResult(BaseModel):
    """
    Результат выполнения действия.
    """
    success: bool = Field(..., description="Успешность выполнения")
    data: Optional[Any] = Field(None, description="Данные результата")
    error: Optional[str] = Field(None, description="Сообщение об ошибке")
    
    class Config:
        arbitrary_types_allowed = True


class SessionStatus(BaseModel):
    """
    Статус Stateful сессии.
    """
    session_id: str
    active: bool
    created_at: float
    last_activity: float
    proxy: Optional[str] = None
