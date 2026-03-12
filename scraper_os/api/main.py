"""
api/main.py — FastAPI Application Entry Point.

Combines REST routers and WebSocket endpoints.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from scraper_os.api.routers import stateless, sessions
from scraper_os.api.websockets.manager import WebSocketSessionManager
from scraper_os.infrastructure.queue.broker import broker
from scraper_os.domain.registry import action_registry
import scraper_os.actions  # Ensure actions are registered for the /actions endpoint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    if not broker.is_worker_process:
        await broker.startup()
    yield
    if not broker.is_worker_process:
        await broker.shutdown()


app = FastAPI(
    title="Atomic Scraper OS API",
    description="Smart Scraping API with LLM orchestration and Stateful Actors.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Routers ──────────────────────────────────────────────────────────
app.include_router(stateless.router)
app.include_router(sessions.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Atomic Scraper OS"}


@app.get("/actions")
async def list_actions():
    """List all registered actions for stateful sessions."""
    return {"actions": action_registry.list_actions()}


# ── WebSockets ───────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    manager = WebSocketSessionManager(websocket, session_id)
    await manager.run()
