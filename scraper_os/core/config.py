"""
Конфигурация приложения через Pydantic Settings.
Хранит настройки прокси, таймаутов, API ключей и т.д.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    """Настройки приложения"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # === Redis ===
    REDIS_URL: str = "redis://localhost:6379"
    
    # === API Keys ===
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    JINA_API_KEY: Optional[str] = None
    JINA_BASE_URL: str = "https://huggingface.co/jinav2/reader-v2/resolve/main"
    
    # === Серверный пул прокси (для Stateless задач) ===
    # Формат: ["http://user:pass@host:port", "socks5://user:pass@host:port"]
    SERPER_PROXIES: List[str] = []
    SCRAPER_PROXIES: List[str] = []
    
    # === Таймауты ===
    SESSION_TIMEOUT_SECONDS: int = 300  # 5 минут бездействия = закрытие сессии
    REQUEST_TIMEOUT_SECONDS: int = 30   # Таймаут одного HTTP запроса
    PLAYWRIGHT_TIMEOUT_SECONDS: int = 30000  # 30 секунд на операции Playwright
    
    # === Playwright ===
    HEADLESS_DEFAULT: bool = True
    CHROMIUM_CHANNEL: str = "chromium"
    
    # === Окно браузера по умолчанию ===
    DEFAULT_WINDOW_WIDTH: int = 1920
    DEFAULT_WINDOW_HEIGHT: int = 1080
    
    # === Логирование ===
    LOG_LEVEL: str = "INFO"
    
    @property
    def has_server_proxies(self) -> bool:
        """Есть ли серверные прокси для Stateless задач"""
        return bool(self.SERPER_PROXIES or self.SCRAPER_PROXIES)
    
    def get_next_proxy(self, proxy_type: str = "scraper", current_index: int = 0) -> tuple[str, int]:
        """
        Round-robin выборка прокси из пула.
        Возвращает (proxy, next_index)
        """
        proxies = self.SCRAPER_PROXIES if proxy_type == "scraper" else self.SERPER_PROXIES
        if not proxies:
            return "", 0
        proxy = proxies[current_index % len(proxies)]
        return proxy, (current_index + 1) % len(proxies)


settings = Settings()
