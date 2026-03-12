"""
api/websockets/manager.py — WebSocket to Redis Bridge.

Transmits client commands to the Session Actor via Redis Pub/Sub
and streams actor results back to the client.
"""

import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


class WebSocketSessionManager:
    """Manages a single WebSocket connection to a stateful session."""

    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.redis = redis.from_url(settings.redis_url)
        self.res_channel = f"res:{self.session_id}"
        self.cmd_channel = f"cmd:{self.session_id}"

    async def run(self):
        """Main loop for the WS connection."""
        await self.websocket.accept()
        logger.info("WebSocket connected for session %s", self.session_id)

        # Start a background task to listen to Redis results
        listen_task = asyncio.create_task(self._listen_to_redis())

        try:
            while True:
                # 1. Listen for commands from the client (WS)
                data = await self.websocket.receive_text()

                # 2. Publish to Redis cmd channel
                await self.redis.publish(self.cmd_channel, data)
                logger.debug("Published command to %s: %s", self.cmd_channel, data)

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected for session %s", self.session_id)
        except Exception as exc:
            logger.error("WebSocket error for session %s: %s", self.session_id, exc)
        finally:
            listen_task.cancel()
            await self.redis.close()

    async def _listen_to_redis(self):
        """Listener that forwards Redis results to the WebSocket."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.res_channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Forward the data directly as text
                    await self.websocket.send_text(message["data"].decode("utf-8"))
        except Exception as exc:
            logger.error(
                "Redis listener error for session %s: %s", self.session_id, exc
            )
        finally:
            await pubsub.unsubscribe(self.res_channel)
            await pubsub.close()
