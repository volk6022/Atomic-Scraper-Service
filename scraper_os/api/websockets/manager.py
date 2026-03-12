"""
WebSocket Manager - транслятор между WebSocket и Redis Pub/Sub.

Управляет WebSocket соединениями и транслирует:
- Клиент -> Redis Pub/Sub (канал cmd:{session_id})
- Redis Pub/Sub (канал res:{session_id}) -> Клиент
"""
import logging
import asyncio
import json
from typing import Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect

import redis.asyncio as redis

from core.config import settings

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Менеджер WebSocket соединений для Stateful сессий.
    
    Для каждой сессии:
    1. Подключается к Redis Pub/Sub (канал результатов res:{id})
    2. Транслирует сообщения от клиента в Redis (канал cmd:{id})
    3. Транслирует сообщения от Redis клиенту
    """
    
    def __init__(self):
        self._active_connections: Dict[str, Set[WebSocket]] = {}
        self._redis_tasks: Dict[str, asyncio.Task] = {}
        self._redis_client: Optional[redis.Redis] = None
    
    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Подключить WebSocket к сессии.
        
        Args:
            websocket: WebSocket соединение
            session_id: ID сессии
        """
        await websocket.accept()
        
        # Инициализация Redis если нужно
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        
        # Добавляем соединение в активные
        if session_id not in self._active_connections:
            self._active_connections[session_id] = set()
        self._active_connections[session_id].add(websocket)
        
        logger.info(f"WebSocket connected to session {session_id}")
        
        # Запускаем задачу прослушивания Redis
        if session_id not in self._redis_tasks:
            self._redis_tasks[session_id] = asyncio.create_task(
                self._listen_redis(session_id)
            )
        
        # Запускаем задачу прослушивания клиента
        asyncio.create_task(self._listen_client(websocket, session_id))
    
    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Отключить WebSocket от сессии.
        
        Args:
            websocket: WebSocket соединение
            session_id: ID сессии
        """
        if session_id in self._active_connections:
            self._active_connections[session_id].discard(websocket)
            
            if not self._active_connections[session_id]:
                # Последнее соединение отключено
                del self._active_connections[session_id]
                
                # Отменяем задачу Redis (но не убиваем сессию!)
                if session_id in self._redis_tasks:
                    self._redis_tasks[session_id].cancel()
                    del self._redis_tasks[session_id]
        
        logger.info(f"WebSocket disconnected from session {session_id}")
    
    async def _listen_redis(self, session_id: str) -> None:
        """
        Слушать Redis Pub/Sub и отправлять сообщения клиентам.
        
        Args:
            session_id: ID сессии
        """
        pubsub = self._redis_client.pubsub()
        
        try:
            await pubsub.subscribe(f"res:{session_id}")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Трансляция всем подключенным клиентам
                    data = message["data"]
                    await self._broadcast(session_id, data)
                    
        except asyncio.CancelledError:
            logger.debug(f"Redis listener cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Redis listener error for {session_id}: {e}")
        finally:
            await pubsub.unsubscribe(f"res:{session_id}")
            await pubsub.close()
    
    async def _listen_client(self, websocket: WebSocket, session_id: str) -> None:
        """
        Слушать клиента и публиковать команды в Redis.
        
        Args:
            websocket: WebSocket соединение
            session_id: ID сессии
        """
        try:
            async for message in websocket.iter_text():
                # Публикация команды в Redis
                await self._redis_client.publish(f"cmd:{session_id}", message)
                logger.debug(f"Command published to cmd:{session_id}")
                
        except WebSocketDisconnect:
            logger.info(f"Client disconnected from session {session_id}")
        except Exception as e:
            logger.error(f"Client listener error for {session_id}: {e}")
    
    async def _broadcast(self, session_id: str, data: str) -> None:
        """
        Отправить сообщение всем подключенным клиентам сессии.
        
        Args:
            session_id: ID сессии
            data: Данные для отправки
        """
        if session_id not in self._active_connections:
            return
        
        disconnected = set()
        
        for websocket in self._active_connections[session_id]:
            try:
                await websocket.send_text(data)
            except Exception:
                disconnected.add(websocket)
        
        # Удаляем отключенные
        for ws in disconnected:
            self._active_connections[session_id].discard(ws)
    
    async def send_session_status(
        self,
        session_id: str,
        status: str,
        **kwargs,
    ) -> None:
        """
        Отправить статус сессии.
        
        Args:
            session_id: ID сессии
            status: Статус (started, closed, error, etc.)
            **kwargs: Дополнительные данные
        """
        message = json.dumps({"status": status, **kwargs})
        
        if session_id in self._active_connections:
            for websocket in self._active_connections[session_id]:
                try:
                    await websocket.send_text(message)
                except Exception:
                    pass
    
    def get_active_connections(self, session_id: str) -> int:
        """
        Получить количество активных подключений к сессии.
        
        Args:
            session_id: ID сессии
        
        Returns:
            Количество подключений
        """
        return len(self._active_connections.get(session_id, set()))


# Глобальный менеджер
ws_manager = WebSocketManager()
