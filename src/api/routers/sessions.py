from fastapi import APIRouter, Depends, HTTPException
from src.api.auth import get_api_key
from src.infrastructure.queue.session_actor import run_session_actor
from src.api.websockets.manager import manager
from src.core.config import settings
from pydantic import BaseModel
from typing import Any, Dict, Optional
import asyncio
import json
import uuid


router = APIRouter(dependencies=[Depends(get_api_key)])

# Timeout for waiting on a command result via the HTTP endpoint (seconds).
# Kept well below SESSION_INACTIVITY_TIMEOUT so the actor never expires mid-wait.
COMMAND_TIMEOUT = 60.0


class CommandRequest(BaseModel):
    type: str
    params: Optional[Dict[str, Any]] = {}


@router.post("/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    # Start the session actor in the background
    await run_session_actor.kiq(session_id)
    return {"session_id": session_id, "status": "active"}


@router.post("/sessions/{session_id}/command")
async def send_command(session_id: str, command: CommandRequest):
    """
    Send a single DSL command to an active session and return the result.

    Publishes the command to the Redis ``cmd:{session_id}`` channel (same
    channel the WebSocket handler uses), then subscribes to ``res:{session_id}``
    for a one-shot result.  The connection is closed immediately after the
    first result message is received or after COMMAND_TIMEOUT seconds.

    This endpoint is the recommended interface for MCP / programmatic clients
    that cannot maintain a persistent WebSocket connection.
    """
    payload = command.model_dump()

    # Subscribe *before* publishing so we never miss the response.
    pubsub = await manager.subscribe_results(session_id)
    try:
        await manager.publish_command(session_id, payload)

        deadline = asyncio.get_event_loop().time() + COMMAND_TIMEOUT
        async for message in pubsub.listen():
            if asyncio.get_event_loop().time() > deadline:
                raise HTTPException(
                    status_code=504, detail="Command timed out waiting for result"
                )
            if message["type"] == "message":
                return json.loads(message["data"])
    finally:
        await pubsub.unsubscribe(f"res:{session_id}")

    raise HTTPException(status_code=504, detail="Command timed out waiting for result")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    # Send a special command to the actor to stop
    await manager.publish_command(session_id, {"type": "stop"})
    return {
        "status": "success",
        "message": f"Session {session_id} termination signal sent",
    }
