"""Contract tests for research endpoint - TDD RED (expected to fail)"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient
import json


@pytest.fixture
def app_with_research():
    """Create FastAPI app with research router"""
    from src.api.main import app
    from src.api.routers import research

    app.include_router(research.router, prefix="/api/v1")
    return app


class TestResearchRunEndpoint:
    """Test POST /api/v1/research/run endpoint"""

    @pytest.mark.asyncio
    async def test_post_run_returns_202_with_task_id(self, app_with_research):
        """POST /research/run with valid body + API key should return 202 with task_id"""
        transport = ASGITransport(app=app_with_research)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/research/run",
                json={"query": "What are the latest trends in AI?"},
                headers={"X-API-Key": "default_internal_key"},
            )

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_post_run_without_api_key_returns_401(self, app_with_research):
        """POST /research/run without API key should return 401"""
        transport = ASGITransport(app=app_with_research)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/research/run", json={"query": "What is AI?"}
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_post_run_with_invalid_mode_returns_422(self, app_with_research):
        """POST /research/run with invalid mode should return 422"""
        transport = ASGITransport(app=app_with_research)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/research/run",
                json={"query": "What is AI?", "mode": "invalid_mode"},
                headers={"X-API-Key": "default_internal_key"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_run_with_5_concurrent_tasks_returns_429(
        self, app_with_research
    ):
        """POST /research/run when API key has 5 running tasks should return 429"""
        with patch("src.api.routers.research.get_concurrent_task_count") as mock_count:
            mock_count.return_value = 5

            transport = ASGITransport(app=app_with_research)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/research/run",
                    json={"query": "What is AI?"},
                    headers={"X-API-Key": "default_internal_key"},
                )

            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_post_run_validates_query_min_length(self, app_with_research):
        """POST /research/run should reject queries shorter than 3 chars"""
        transport = ASGITransport(app=app_with_research)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/research/run",
                json={"query": "ab"},
                headers={"X-API-Key": "default_internal_key"},
            )

        assert response.status_code == 422


class TestResearchStatusEndpoint:
    """Test GET /api/v1/research/status/{task_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_status_running_returns_progress(self, app_with_research):
        """GET /status/{task_id} while running should return progress"""
        with patch("src.api.routers.research.get_research_task") as mock_get:
            mock_get.return_value = {
                "task_id": "test-123",
                "status": "running",
                "phase": "searching",
                "iteration": 2,
                "created_at": "2026-05-11T12:00:00Z",
            }

            transport = ASGITransport(app=app_with_research)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/research/status/test-123",
                    headers={"X-API-Key": "default_internal_key"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "progress" in data

    @pytest.mark.asyncio
    async def test_get_status_completed_returns_report(self, app_with_research):
        """GET /status/{task_id} after completion should return ResearchReport"""
        with patch("src.api.routers.research.get_research_task") as mock_get:
            mock_get.return_value = {
                "task_id": "test-123",
                "status": "completed",
                "result": {
                    "query": "What is AI?",
                    "mode": "balanced",
                    "answer_markdown": "AI is [1] artificial intelligence.",
                    "citations": [
                        {"url": "https://example.com", "title": "AI", "snippet": "..."}
                    ],
                    "facts": [
                        {
                            "claim": "AI is intelligence",
                            "confidence": 0.9,
                            "source_url": "https://example.com",
                        }
                    ],
                    "stats": {
                        "iterations": 5,
                        "urls_visited": 12,
                        "elapsed_seconds": 184.5,
                        "mode_used": "balanced",
                        "completed_normally": True,
                    },
                },
                "created_at": "2026-05-11T12:00:00Z",
                "updated_at": "2026-05-11T12:03:04Z",
            }

            transport = ASGITransport(app=app_with_research)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/research/status/test-123",
                    headers={"X-API-Key": "default_internal_key"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "result" in data
        assert "answer_markdown" in data["result"]
        assert "citations" in data["result"]
        assert "facts" in data["result"]
        assert "stats" in data["result"]

    @pytest.mark.asyncio
    async def test_get_status_fake_id_returns_404(self, app_with_research):
        """GET /status/{fake_id} should return 404"""
        with patch("src.api.routers.research.get_research_task") as mock_get:
            mock_get.return_value = None

            transport = ASGITransport(app=app_with_research)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/research/status/non-existent-id",
                    headers={"X-API-Key": "default_internal_key"},
                )

        assert response.status_code == 404


class TestResearchStreamEndpoint:
    """Test GET /api/v1/research/stream/{task_id} endpoint (US4)"""

    @pytest.mark.asyncio
    async def test_get_stream_returns_sse_events(self, app_with_research):
        """GET /stream/{task_id} should return SSE events"""
        with patch("src.api.routers.research.get_research_task") as mock_get:
            mock_get.return_value = {
                "task_id": "test-123",
                "status": "running",
                "phase": "searching",
                "iteration": 2,
                "created_at": "2026-05-11T12:00:00Z",
            }

            transport = ASGITransport(app=app_with_research)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/research/stream/test-123",
                    headers={"X-API-Key": "default_internal_key"},
                )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
