"""
infrastructure/queue/actor_workers.py — Stateful Session Actor.

Implements the long-running worker that maintains a live browser session,
listening for commands via Redis Pub/Sub and executing them.
"""

import asyncio
import logging
import json
import time
from typing import Any

import redis.asyncio as redis
from scraper_os.infrastructure.queue.broker import broker
from scraper_os.infrastructure.browser.session_manager import SessionBrowserManager
from scraper_os.domain.models.requests import SessionConfig, CommandPayload
from scraper_os.domain.models.dsl import ActionResult, ActionStatus
from scraper_os.domain.registry import action_registry
import scraper_os.actions  # Ensure all actions are registered
from scraper_os.infrastructure.llm.facade import LLMFacade
from scraper_os.core.config import settings

logger = logging.getLogger(__name__)


@broker.task
async def run_stateful_session(session_id: str, config: SessionConfig) -> None:
    """Long-lived task that manages a stateful browser session.

    This 'Actor' runs until:
    1. It receives a 'close' command.
    2. It hits the inactivity timeout (settings.session_timeout_seconds).
    3. It hits the absolute max duration (settings.session_max_duration_seconds).
    """
    logger.info("Starting stateful actor for session %s", session_id)

    # 1. Initialize isolated browser
    browser_manager = SessionBrowserManager(config)
    page = await browser_manager.init()

    # 2. Setup Redis Pub/Sub
    redis_client = redis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()

    cmd_channel = f"cmd:{session_id}"
    res_channel = f"res:{session_id}"

    await pubsub.subscribe(cmd_channel)
    logger.debug("Subscribed to %s", cmd_channel)

    last_active = time.time()
    start_time = time.time()

    # Initialize LLMFacade for AI-powered actions
    llm_facade = LLMFacade()

    try:
        while True:
            # ── Check Timeouts ───────────────────────────────────────
            now = time.time()

            # Inactivity timeout
            if now - last_active > settings.session_timeout_seconds:
                logger.warning("Session %s timed out due to inactivity.", session_id)
                break

            # Absolute max duration
            if now - start_time > settings.session_max_duration_seconds:
                logger.warning("Session %s reached max duration.", session_id)
                break

            # ── Wait for Commands ────────────────────────────────────
            # We use a short timeout in get_message so we can check the
            # loop conditions (timeouts) periodically.
            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if msg and msg["type"] == "message":
                    last_active = time.time()
                    data = msg["data"]

                    # Parse command
                    try:
                        # Redis gives us bytes, we expect JSON string
                        payload_dict = json.loads(data.decode("utf-8"))
                        payload = CommandPayload(**payload_dict)
                    except Exception as exc:
                        logger.error("Failed to parse command payload: %s", exc)
                        error_res = ActionResult.fail(
                            "parse", f"Invalid JSON or payload: {exc}"
                        )
                        await redis_client.publish(
                            res_channel, error_res.model_dump_json()
                        )
                        continue

                    # Handle 'exit' command explicitly
                    if payload.action == "exit":
                        logger.info("Session %s received exit command.", session_id)
                        await redis_client.publish(
                            res_channel, ActionResult.ok("exit").model_dump_json()
                        )
                        break

                    # ── Execute Action ───────────────────────────────────
                    logger.info(
                        "Session %s executing action: %s", session_id, payload.action
                    )

                    try:
                        action_cls = action_registry.get(payload.action)
                        action_instance = action_cls()

                        # Execute the action
                        result = await action_instance.execute(
                            page=page, params=payload.params, llm_facade=llm_facade
                        )

                        # Publish result back
                        await redis_client.publish(
                            res_channel, result.model_dump_json()
                        )

                    except KeyError as exc:
                        logger.error("Unknown action: %s", payload.action)
                        error_res = ActionResult.fail(payload.action, str(exc))
                        await redis_client.publish(
                            res_channel, error_res.model_dump_json()
                        )
                    except Exception as exc:
                        logger.exception("Action execution failed: %s", payload.action)
                        error_res = ActionResult.fail(
                            payload.action, f"Internal error: {exc}"
                        )
                        await redis_client.publish(
                            res_channel, error_res.model_dump_json()
                        )

            except asyncio.TimeoutError:
                # Normal timeout from get_message, just continue the loop
                continue
            except Exception as exc:
                logger.error("Error in actor loop: %s", exc)
                await asyncio.sleep(1)  # Prevent tight loop on Redis error

    finally:
        # 3. Cleanup
        await pubsub.unsubscribe(cmd_channel)
        await pubsub.close()
        await redis_client.close()
        await browser_manager.close()
        logger.info("Stateful actor for session %s terminated.", session_id)
