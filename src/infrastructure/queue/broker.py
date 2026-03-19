from taskiq_redis import ListQueueBroker
from src.core.config import settings

broker = ListQueueBroker(settings.REDIS_URL)
