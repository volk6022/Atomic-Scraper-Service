# Core Configuration

Application-wide settings and constants managed via Pydantic BaseSettings.

- `config.py`: Central configuration class. Handles Redis URLs, proxy pools, session timeouts, and LLM API keys.
- Environment variables: Use `SCRAPER_` prefix (e.g., `SCRAPER_REDIS_URL`).
