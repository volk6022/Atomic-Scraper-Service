"""
api/routers/sessions.py — REST endpoints for Circuit B (Stateful Actors).

Manages the lifecycle of long-lived interactive sessions.
"""

import uuid
from fastapi import APIRouter, HTTPException
from scraper_os.domain.models.requests import SessionCreateRequest
from scraper_os.domain.models.dsl import SessionInfo
from scraper_os.infrastructure.queue.actor_workers import run_stateful_session
import redis.asyncio as redis
from scraper_os.core.config import settings

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionInfo)
async def create_session(request: SessionCreateRequest):
    """Create a new stateful session actor."""
    session_id = str(uuid.uuid4())

    # 1. Enqueue the actor task (it will run until timeout or exit)
    await run_stateful_session.kiq(session_id, request.config)

    # 2. Store metadata in Redis (optional but good for tracking)
    # We could use a hash here
    redis_client = redis.from_url(settings.redis_url)
    await redis_client.hset(
        f"session_meta:{session_id}",
        mapping={"status": "active", "config": request.config.model_dump_json()},
    )
    await redis_client.close()

    return SessionInfo(
        session_id=session_id, status="active", config=request.config.model_dump()
    )


@router.delete("/{session_id}")
async def terminate_session(session_id: str):
    """Terminate a session by sending an 'exit' command via Pub/Sub."""
    redis_client = redis.from_url(settings.redis_url)

    # Send exit command to the actor
    await redis_client.publish(f"cmd:{session_id}", '{"action": "exit"}')

    # Update metadata
    await redis_client.hset(f"session_meta:{session_id}", "status", "closing")
    await redis_client.close()

    return {"status": "termination_signal_sent"}
