import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# Add yandex_enrichment_experiment to path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from review_app.app import app


@pytest.fixture
async def client():
    """Async HTTP client for testing the FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
def pg_container():
    """PostgreSQL container for integration tests."""
    pytest.importorskip("testcontainers")
    from testcontainers.postgres import PostgresContainer

    try:
        container = PostgresContainer("postgres:16")
        container.start()
        yield container
        container.stop()
    except Exception as e:
        pytest.skip(reason=f"Docker unavailable: {e}")


@pytest.fixture
async def pg_session(pg_container, monkeypatch):
    """Async session connected to test PostgreSQL container."""
    pytest.importorskip("testcontainers")
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    # Convert container URL to asyncpg URL
    container_url = pg_container.get_connection_url()
    # Replace psycopg2 driver with asyncpg
    asyncpg_url = container_url.replace("postgresql://", "postgresql+asyncpg://")

    # Monkeypatch the settings to use the test database URL
    monkeypatch.setenv("REVIEW_DB_URL", asyncpg_url)
    from review_app.config import get_settings
    get_settings.cache_clear()

    try:
        # Import after path is set up
        from review_app.db import get_session
        from review_app.schema_sql import bootstrap_schema
        from sqlalchemy import text

        # Create engine and apply schema
        engine = create_async_engine(asyncpg_url)
        async with engine.begin() as conn:
            await bootstrap_schema(conn)

        # Create session factory
        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_factory() as session:
            yield session

    finally:
        get_settings.cache_clear()
