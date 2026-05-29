import json

import pytest


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        """Test that GET /health returns 200 with correct JSON."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}


class TestRoot:
    @pytest.mark.asyncio
    async def test_root_returns_html(self, client):
        """Test that GET / returns HTML."""
        response = await client.get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")


class TestStaticFiles:
    @pytest.mark.asyncio
    async def test_static_css_coridoor_tokens_served(self, client):
        """Test that /static/css/coridoor-tokens.css is served."""
        response = await client.get("/static/css/coridoor-tokens.css")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
        assert len(response.text) > 1000

    @pytest.mark.asyncio
    async def test_static_styles_css_served(self, client):
        """Test that /static/css/styles.css is served."""
        response = await client.get("/static/css/styles.css")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
        assert len(response.text) > 1000
