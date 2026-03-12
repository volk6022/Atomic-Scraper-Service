"""
infrastructure/queue/broker.py — Taskiq broker configuration.

Sets up the Redis broker for distributing scraping tasks and managing
stateful actor lifecycles.
"""

import taskiq_fastapi
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker
from scraper_os.core.config import settings

# ── Result Backend ───────────────────────────────────────────────────
# Stores the results of stateless tasks (/scrape, /serper)
result_backend = RedisAsyncResultBackend(
    redis_url=settings.redis_url,
)

# ── Broker ───────────────────────────────────────────────────────────
# Manages the task queue. We use ListQueueBroker (Redis LIST) for simplicity.
broker = ListQueueBroker(
    url=settings.redis_url,
    result_backend=result_backend,
).with_result_backend(result_backend)

# FastAPI integration
taskiq_fastapi.init(broker, "scraper_os.api.main:app")


@broker.on_event("startup")
async def startup_event() -> None:
    """Initialize resources on worker startup."""
    # This is where we will start the BrowserPoolManager for stateless workers
    from scraper_os.infrastructure.browser.pool_manager import BrowserPoolManager

    # We only want to start the pool if this is a stateless worker process.
    # In a real scenario, we might use environment variables to distinguish.
    # For now, we'll initialize it, and it will be a no-op if already started.
    await BrowserPoolManager.start()


@broker.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup resources on worker shutdown."""
    from scraper_os.infrastructure.browser.pool_manager import BrowserPoolManager

    await BrowserPoolManager.stop()
