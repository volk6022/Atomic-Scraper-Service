from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.api.routers import stateless, sessions, health
from src.api.websockets import handler
from src.infrastructure.browser.pool_manager import pool_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await pool_manager.close()


app = FastAPI(title="Smart Scraping LLM API", lifespan=lifespan)

app.include_router(stateless.router)
app.include_router(sessions.router)
app.include_router(health.router)
app.include_router(handler.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
