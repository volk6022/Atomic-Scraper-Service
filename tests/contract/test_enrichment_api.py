"""
Contract test for enrichment API endpoint.
T029: Write failing contract test for enrichment API.

This test MUST fail before implementation (TDD requirement).
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from src.domain.models.enriched_content import EnrichedContent

TEST_API_KEY = "default_internal_key"


def get_mock_enriched(
    text="Sample company content about services.",
    word_count=5,
    truncated=False,
    pages_crawled=None,
):
    return EnrichedContent(
        url="https://example.com",
        text=text,
        word_count=word_count,
        truncated=truncated,
        pages_crawled=pages_crawled,
    )


@pytest.mark.asyncio
async def test_enrichment_endpoint_returns_200():
    """Enrichment endpoint should return 200 OK"""
    from src.api.main import app

    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_enrichment_response_format():
    """Enrichment should return proper response format"""
    from src.api.main import app

    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200
            data = response.json()
            assert "url" in data
            assert "text" in data
            assert "word_count" in data
            assert "truncated" in data


@pytest.mark.asyncio
async def test_enrichment_text_is_clean():
    """Enrichment text should be clean (not raw HTML)"""
    from src.api.main import app

    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200
            data = response.json()
            text = data["text"]
            assert "<html" not in text.lower()
            assert "<div" not in text.lower()


@pytest.mark.asyncio
async def test_enrichment_word_limit():
    """Enrichment should respect word limit (≤500 words)"""
    from src.api.main import app

    long_text = "word " * 300
    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(text=long_text, word_count=300),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200
            data = response.json()
            word_count = data["word_count"]
            assert word_count <= 510


@pytest.mark.asyncio
async def test_enrichment_missing_url():
    """Missing URL should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/enrich",
            json={},
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_enrichment_invalid_url():
    """Invalid URL should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/enrich",
            json={
                "url": "not-a-valid-url",
            },
            headers={"X-API-Key": TEST_API_KEY},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_enrichment_with_crawl_options():
    """Enrichment should support crawl options for about/services pages"""
    from src.api.main import app

    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(
            pages_crawled=["https://example.com", "https://example.com/about"]
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                    "crawl_about": True,
                    "crawl_services": True,
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200
            data = response.json()
            assert "pages_crawled" in data


@pytest.mark.asyncio
async def test_enrichment_truncated_flag():
    """Enrichment should set truncated flag when content exceeds limit"""
    from src.api.main import app

    with patch(
        "src.actions.site_enricher.SiteEnrichAction.execute",
        new_callable=AsyncMock,
        return_value=get_mock_enriched(truncated=True, word_count=500),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/enrich",
                json={
                    "url": "https://example.com",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data["truncated"], bool)
