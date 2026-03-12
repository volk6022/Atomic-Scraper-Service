"""
Actor Workers - воркеры для Stateful сессий.

Каждая сессия запускается в отдельном акторе с собственным браузером.
Реализована логика таймаута бездействия.
"""
import asyncio
import time
import logging
import json
from typing import Dict, Any, Optional

import redis.asyncio as redis

from infrastructure.queue.broker import broker
from infrastructure.browser.session_manager import SessionBrowserManager
from domain.models import SessionConfig, CommandPayload, ActionResult
from domain.registry import registry
from core.config import settings

logger = logging.getLogger(__name__)


# Глобальный Redis клиент для actor workers
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Получить Redis клиент (singleton per worker)"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


@broker.task
async def run_stateful_session(
    session_id: str,
    config_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Запустить Stateful сессию.
    
    Актор создаёт собственный браузер, подписывается на Redis Pub/Sub
    и выполняет команды от клиента. Сессия завершается по таймауту
    бездействия или при принудительном закрытии.
    
    Args:
        session_id: Уникальный ID сессии
        config_dict: Конфигурация сессии (SessionConfig в виде dict)
    
    Returns:
        Статус завершения сессии
    """
    config = SessionConfig(**config_dict)
    last_active = time.time()
    browser_manager = None
    redis_client = None
    
    logger.info(f"Starting stateful session: {session_id}")
    
    try:
        # 1. Инициализация браузера сессии
        browser_manager = SessionBrowserManager(config)
        page = await browser_manager.init()
        
        # 2. Подключение к Redis
        redis_client = await get_redis()
        
        # 3. Публикация события запуска
        await redis_client.publish(
            f"session:{session_id}:status",
            json.dumps({"status": "started", "session_id": session_id}),
        )
        
        # 4. Основной цикл обработки команд
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"cmd:{session_id}")
        
        logger.info(f"Session {session_id} listening for commands...")
        
        while True:
            # Проверка таймаута бездействия
            elapsed = time.time() - last_active
            if elapsed > settings.SESSION_TIMEOUT_SECONDS:
                logger.warning(
                    f"Session {session_id} timeout ({elapsed:.0f}s > "
                    f"{settings.SESSION_TIMEOUT_SECONDS}s). Killing."
                )
                break
            
            # Ожидание команды с таймаутом 1 секунда (для проверки heartbeat)
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    ),
                    timeout=1.0,
                )
                
                if message and message.get("type") == "message":
                    # Обновление времени последней активности
                    last_active = time.time()
                    
                    # Парсинг команды
                    try:
                        data = json.loads(message["data"])
                        payload = CommandPayload(**data)
                        
                        logger.debug(
                            f"Session {session_id} executing: "
                            f"{payload.action} with {payload.params}"
                        )
                        
                        # Выполнение действия через Registry
                        action = registry.create(payload.action)
                        
                        if action is None:
                            result = ActionResult(
                                success=False,
                                error=f"Unknown action: {payload.action}",
                            )
                        else:
                            # Импортируем LLMFacade только если нужен
                            llm_facade = None
                            if payload.action.startswith("ai_") or "omni" in payload.action.lower():
                                from infrastructure.llm.facade import LLMFacade
                                llm_facade = LLMFacade()
                            
                            result_data = await action.execute(
                                page,
                                payload.params,
                                llm_facade,
                            )
                            result = ActionResult(**result_data) if isinstance(result_data, dict) else result_data
                        
                        # Публикация результата
                        await redis_client.publish(
                            f"res:{session_id}",
                            result.model_dump_json(),
                        )
                        
                        # Публикация события активности
                        await redis_client.publish(
                            f"session:{session_id}:status",
                            json.dumps({
                                "status": "active",
                                "last_action": payload.action,
                                "timestamp": time.time(),
                            }),
                        )
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in command: {e}")
                        error_result = ActionResult(
                            success=False,
                            error=f"Invalid JSON: {str(e)}",
                        )
                        await redis_client.publish(
                            f"res:{session_id}",
                            error_result.model_dump_json(),
                        )
                        
                    except Exception as e:
                        logger.error(f"Error executing action: {e}")
                        error_result = ActionResult(
                            success=False,
                            error=str(e),
                        )
                        await redis_client.publish(
                            f"res:{session_id}",
                            error_result.model_dump_json(),
                        )
                
            except asyncio.TimeoutError:
                # Таймаут wait_for - просто продолжаем цикл
                continue
        
        # Выход из цикла по таймауту
        await redis_client.publish(
            f"session:{session_id}:status",
            json.dumps({
                "status": "timeout",
                "session_id": session_id,
                "reason": f"No activity for {settings.SESSION_TIMEOUT_SECONDS}s",
            }),
        )
        
    except Exception as e:
        logger.error(f"Fatal error in session {session_id}: {e}")
        if redis_client:
            await redis_client.publish(
                f"session:{session_id}:status",
                json.dumps({
                    "status": "error",
                    "session_id": session_id,
                    "error": str(e),
                }),
            )
    
    finally:
        # 5. Очистка ресурсов
        logger.info(f"Cleaning up session {session_id}")
        
        if browser_manager:
            await browser_manager.close()
        
        # Отписка от каналов
        if redis_client:
            try:
                await redis_client.publish(
                    f"session:{session_id}:status",
                    json.dumps({"status": "closed", "session_id": session_id}),
                )
            except Exception:
                pass
        
        logger.info(f"Session {session_id} closed")
    
    return {
        "session_id": session_id,
        "status": "closed",
    }


@broker.task
async def kill_session(session_id: str) -> Dict[str, Any]:
    """
    Принудительно завершить сессию.
    
    Отправляет команду завершения в канал сессии.
    
    Args:
        session_id: ID сессии для завершения
    
    Returns:
        Статус операции
    """
    redis_client = await get_redis()
    
    # Публикация команды завершения (специальное действие)
    await redis_client.publish(
        f"cmd:{session_id}",
        json.dumps({"action": "__kill__", "params": {}}),
    )
    
    logger.info(f"Kill command sent to session {session_id}")
    
    return {
        "success": True,
        "session_id": session_id,
        "message": "Kill command sent",
    }
