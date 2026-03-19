from fastapi import APIRouter, Depends
from src.api.auth import get_api_key
import uuid
import time

router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/sessions")
async def create_session():
    session_id = str(uuid.uuid4())
    # In a real implementation, we would trigger a Taskiq actor here
    return {"session_id": session_id, "status": "active"}
