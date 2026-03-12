"""
FastAPI Application - главная точка входа API.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from infrastructure.queue.broker import init_taskiq_fastapi
from api.routers.stateless import router as stateless_router
from api.routers.sessions import router as sessions_router

# Настройка логирования
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Управление жизненным циклом приложения.
    
    Инициализация и очистка ресурсов.
    """
    logger.info("Starting Scraper API...")
    
    # Инициализация Taskiq-FastAPI интеграции
    init_taskiq_fastapi(app)
    
    logger.info("Scraper API started successfully")
    
    yield
    
    logger.info("Shutting down Scraper API...")


# Создание FastAPI приложения
app = FastAPI(
    title="Atomic Scraper API",
    description="Умный скрапинг-API с LLM-оркестрацией",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация роутеров
app.include_router(stateless_router)
app.include_router(sessions_router)


@app.get("/health")
async def health_check() -> dict:
    """Проверка здоровья API"""
    return {"status": "healthy"}


@app.get("/")
async def root() -> dict:
    """Корневой эндпоинт"""
    return {
        "name": "Atomic Scraper API",
        "version": "1.0.0",
        "docs": "/docs",
    }
