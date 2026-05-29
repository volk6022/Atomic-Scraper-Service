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

    # Research Agent (flat-loop, simple_agent_v2.1 port)
    # Defaults mirror the production v2.1 values from the batch run. Tunable via .env.
    RESEARCH_COMPACT_TRIGGER_TOKENS: int = 50_000   # auto-compaction trigger (отд. от mode token_budget)
    RESEARCH_MAX_COMPACTIONS: int = 3
    RESEARCH_SOFT_ELIDE_AFTER_TURNS: int = 4
    RESEARCH_REFRASER_EVERY_N_SERPS: int = 15
    RESEARCH_DOMAIN_FAIL_THRESHOLD: int = 3
    RESEARCH_LLM_TIMEOUT_S: float = 180.0
    RESEARCH_SCRAPE_BUDGET_CHARS: int = 3500
    RESEARCH_CRITIC_PASS_SCORE: float = 8.5
    RESEARCH_MAX_SUBMIT_REJECTS: int = 2
    RESEARCH_DEFAULT_LANGUAGE: str = "ru"
    RESEARCH_DEFAULT_SERP_K: int = 6
    # CSV of domains never auto-blocked even after repeated scrape failures (key infra).
    RESEARCH_DOMAINS_NEVER_BLOCK: str = (
        "yandex.ru,yandex.com,2gis.ru,hh.ru,spb.hh.ru,superjob.ru,vk.com,"
        "t.me,telegram.me,rusprofile.ru,fparf.ru,checko.ru,zoon.ru"
    )
    RESEARCH_PROMPTS_PATH: str = "src/actions/research/research_agent_prompts.yaml"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
