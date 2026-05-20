from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str = "default_internal_key"
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # API Server
    PORT: int = 8000

    # Extraction Settings (e.g., Jina Reader LM)
    EXTRACTION_API_BASE: str = "http://localhost:1234/v1"
    EXTRACTION_API_KEY: str = "lm-studio"
    EXTRACTION_MODEL_NAME: str = "jina-reader-lm"

    # Orchestration Settings (reasoning/navigation)
    ORCHESTRATION_API_BASE: str = "https://api.openai.com/v1"
    ORCHESTRATION_API_KEY: str = "sk-..."
    ORCHESTRATION_MODEL_NAME: str = "gpt-4o"

    # Scraper Settings
    BROWSER_TIMEOUT: int = 30000  # 30 seconds
    SESSION_INACTIVITY_TIMEOUT: int = 600  # 10 minutes
    MAX_CONCURRENT_RESEARCH_TASKS: int = Field(default=5, ge=1, le=100)

    # Rate Limiting Settings
    RATE_LIMIT_YANDEX_PER_HOUR: int = 30
    RATE_LIMIT_DEFAULT_PER_HOUR: int = 1000

    # SearXNG SERP Backend
    # Подтверждено прогонами в serp_experiment/REPORT_searxng.md:
    # VPN на хосте + pool 20 socks5 + retries=2 → 95.3% success.
    # См. infra/searxng/ для docker-compose и settings.yml.
    SEARXNG_BASE_URL: str = "http://localhost:8080"
    SEARXNG_TIMEOUT: float = 30.0       # общий http-timeout клиента
    SEARXNG_MAX_RETRIES: int = 2        # +1 первая попытка = всего 3 attempts
    SEARXNG_RETRY_DELAY: float = 0.5
    SEARXNG_MIN_ORGANIC: int = 1        # минимум organic для счёта «успех» (иначе retry)

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
