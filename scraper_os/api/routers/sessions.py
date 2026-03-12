"""
Sessions Router - REST эндпоинты для управления Stateful сессиями.

Эндпоинты:
- POST /sessions - Создать сессию
- DELETE /sessions/{session_id} - Завершить сессию
- GET /sessions/{session_id}/status - Статус сессии
"""
import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from domain.models import SessionConfig
from infrastructure.queue.broker import broker
from infrastructure.queue.actor_workers import run_stateful_session, kill_session
from api.websockets.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sessions"])

# Хранилище активных сессий (in-memory для простоты)
# В продакшене использовать Redis
_active_sessions: Dict[str, Dict[str, Any]] = {}


@router.post("/sessions")
async def create_session(config: SessionConfig) -> dict:
    """
    Создать новую Stateful сессию.
    
    Запускает actor worker с собственным браузером.
    
    Args:
        config: Конфигурация сессии (proxy, headless, user_agent, etc.)
    
    Returns:
        session_id: Уникальный ID сессии
    """
    session_id = str(uuid.uuid4())
    
    logger.info(f"Creating session: {session_id}")
    
    try:
        # Запуск actor задачи
        await run_stateful_session.kiq(
            session_id=session_id,
            config_dict=config.model_dump(),
        )
        
        # Сохранение информации о сессии
        _active_sessions[session_id] = {
            "config": config.model_dump(),
            "created_at": time.time(),
            "last_activity": time.time(),
            "status": "starting",
        }
        
        logger.info(f"Session {session_id} created")
        
        return {
            "session_id": session_id,
            "status": "starting",
            "message": "Session is starting, connect via WebSocket",
        }
        
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create session: {str(e)}",
        )


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> dict:
    """
    Принудительно завершить сессию.
    
    Отправляет команду kill в actor worker.
    
    Args:
        session_id: ID сессии
    
    Returns:
        Статус операции
    """
    logger.info(f"Closing session: {session_id}")
    
    if session_id not in _active_sessions:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found",
        )
    
    try:
        # Отправка команды kill
        result = await kill_session.kiq(session_id=session_id)
        
        # Удаление из активных
        del _active_sessions[session_id]
        
        logger.info(f"Session {session_id} closed")
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Session closed",
        }
        
    except Exception as e:
        logger.error(f"Error closing session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to close session: {str(e)}",
        )


@router.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str) -> dict:
    """
    Получить статус сессии.
    
    Args:
        session_id: ID сессии
    
    Returns:
        Статус сессии
    """
    if session_id not in _active_sessions:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found",
        )
    
    session_info = _active_sessions[session_id]
    
    return {
        "session_id": session_id,
        "active": True,
        "created_at": session_info["created_at"],
        "last_activity": session_info["last_activity"],
        "proxy": session_info["config"].get("proxy"),
        "headless": session_info["config"].get("headless"),
        "ws_connections": ws_manager.get_active_connections(session_id),
    }


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket эндпоинт для интерактивной сессии.
    
    Клиент отправляет JSON команды, сервер возвращает результаты.
    
    Пример команды:
    {
        "action": "go_to",
        "params": {"url": "https://example.com"}
    }
    
    Пример ответа:
    {
        "success": true,
        "data": {"url": "https://example.com", "title": "Example"},
        "error": null
    }
    """
    if session_id not in _active_sessions:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    try:
        # Подключение через менеджер
        await ws_manager.connect(websocket, session_id)
        
        # Обновление времени последней активности
        _active_sessions[session_id]["last_activity"] = time.time()
        
        # Бесконечный цикл (управление делегировано менеджеру)
        while True:
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
        await ws_manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws_manager.disconnect(websocket, session_id)
