import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import redis.asyncio as redis


@pytest.fixture(autouse=True)
def mock_redis():
    mock_redis_client = MagicMock()  # Use MagicMock for the client
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redis_client.publish = AsyncMock(return_value=1)
    mock_redis_client.close = AsyncMock(return_value=None)

    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock(return_value=None)
    mock_pubsub.unsubscribe = AsyncMock(return_value=None)

    # Define an async generator for listen()
    async def mock_listen():
        yield {
            "type": "message",
            "channel": b"res:test-session",
            "data": b'{"status": "success"}',
        }
        await asyncio.sleep(0.1)

    mock_pubsub.listen = mock_listen
    mock_redis_client.pubsub.return_value = mock_pubsub

    with (
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis_client),
        patch("redis.asyncio.client.Redis.from_url", return_value=mock_redis_client),
    ):
        yield mock_redis_client
