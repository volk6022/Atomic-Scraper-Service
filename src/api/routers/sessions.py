from fastapi import APIRouter, Depends, HTTPException
from src.api.auth import get_api_key
from src.infrastructure.queue.session_actor import run_session_actor
from src.api.websockets.manager import manager
import json
import uuid


router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    # Start the session actor in the background
    await run_session_actor.kiq(session_id)
    return {"session_id": session_id, "status": "active"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    # Send a special command to the actor to stop
    await manager.publish_command(session_id, {"type": "stop"})
    return {
        "status": "success",
        "message": f"Session {session_id} termination signal sent",
    }
