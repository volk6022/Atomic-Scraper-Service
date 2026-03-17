import asyncio
import json
from redis.asyncio import Redis
from src.core.config import settings


class ConnectionManager:
    def __init__(self):
        self._redis = None

    @property
    def redis(self):
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL)
        return self._redis

    async def publish_command(self, session_id: str, command: dict):
        await self.redis.publish(f"cmd:{session_id}", json.dumps(command))

    async def subscribe_results(self, session_id: str):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"res:{session_id}")
        return pubsub


manager = ConnectionManager()
