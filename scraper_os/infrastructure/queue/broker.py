"""
Taskiq Broker - настройка очереди задач с Redis бекендом.
"""
import logging
from typing import Any
from taskiq import AsyncBroker, TaskiqState
from taskiq_redis import RedisBroker, RedisResultBackend
from taskiq_fastapi import TaskiqFastAPI

from core.config import settings

logger = logging.getLogger(__name__)


def create_broker() -> AsyncBroker:
    """
    Создать и настроить Taskiq брокер.
    
    Returns:
        Настроенный AsyncBroker с Redis бекендом
    """
    # Redis broker для очереди задач
    redis_broker = RedisBroker(
        url=settings.REDIS_URL,
        queue_name="scraper_tasks",
    )
    
    # Result backend для получения результатов задач
    result_backend = RedisResultBackend(
        url=settings.REDIS_URL,
    )
    
    # Настройка брокера
    redis_broker = redis_broker.with_result_backend(result_backend)
    
    logger.info(f"Taskiq broker initialized with Redis: {settings.REDIS_URL}")
    
    return redis_broker


# Глобальный экземпляр брокера
broker: AsyncBroker = create_broker()


def init_taskiq_fastapi(app: Any) -> None:
    """
    Инициализировать интеграцию Taskiq с FastAPI.
    
    Args:
        app: FastAPI приложение
    """
    TaskiqFastAPI(broker, app)
    logger.info("Taskiq-FastAPI integration initialized")
