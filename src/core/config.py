from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    API_KEY: str = "default_internal_key"
    REDIS_URL: str = "redis://localhost:6379"

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

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
