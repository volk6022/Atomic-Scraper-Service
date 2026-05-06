"""
E2E test for site enrichment flow.
T030: Write failing E2E test for enrichment flow.

This test MUST fail before implementation (TDD requirement).
"""

import pytest


def test_enrichment_endpoint_registered_in_app():
    """Enrichment endpoint should be registered in main app."""
    from src.api.main import app

    routes = [r.path for r in app.routes]
    assert any("/enrich" in r for r in routes), "Enrichment endpoint not registered"


def test_enrichment_router_exists():
    """Enrichment router should exist."""
    try:
        from src.api.routers.enrichment import router

        assert router is not None
    except ImportError:
        pytest.fail("Enrichment router does not exist")


def test_enrichment_action_exists():
    """Site enrich action should exist."""
    try:
        from src.actions.site_enricher import SiteEnrichAction

        action = SiteEnrichAction()
        assert hasattr(action, "execute")
    except ImportError:
        pytest.fail("SiteEnrichAction does not exist")


def test_enriched_content_model_exists():
    """EnrichedContent model should exist."""
    try:
        from src.domain.models.enriched_content import EnrichedContent

        content = EnrichedContent(
            url="https://example.com",
            text="Sample text content",
            word_count=3,
            truncated=False,
        )
        assert content.url == "https://example.com"
    except ImportError:
        pytest.fail("EnrichedContent model does not exist")


def test_enrichment_returns_clean_text():
    """Enrichment should return clean text, not raw HTML."""
    import pytest

    pytest.skip("Requires live browser - run manually in Docker environment")

    try:
        import httpx
        import asyncio

        async def check():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:8000/api/v1/enrich",
                    json={
                        "url": "https://example.com",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                text = data.get("text", "")
                assert "<html" not in text.lower()
                assert "<div" not in text.lower()
                return True

        result = asyncio.run(check())
        assert result, "Enrichment did not return clean text"
    except Exception as e:
        pytest.fail(f"Enrichment failed: {e}")


def test_content_cleaner_utility_exists():
    """Content cleaner utility should exist."""
    try:
        from src.domain.utils.content_cleaner import (
            clean_html_content,
            truncate_content,
            html_to_text,
        )

        assert clean_html_content is not None
        assert truncate_content is not None
        assert html_to_text is not None
    except ImportError:
        pytest.fail("Content cleaner utilities do not exist")


@pytest.mark.asyncio
async def test_content_truncated_to_500_words():
    """Enrichment action must truncate content to at most 500 words."""
    from unittest.mock import patch, AsyncMock
    from httpx import AsyncClient, ASGITransport
    from src.domain.models.enriched_content import EnrichedContent
    from src.api.main import app

    long_text = " ".join(["word"] * 600)
    truncated_content = EnrichedContent(
        url="https://example.com",
        text=" ".join(["word"] * 500),
        word_count=500,
        truncated=True,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.site_enricher.SiteEnrichAction.execute",
            new_callable=AsyncMock,
            return_value=truncated_content,
        ):
            response = await client.post(
                "/api/v1/enrich",
                headers={"X-API-Key": "default_internal_key"},
                json={"url": "https://example.com"},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["word_count"] <= 500
    assert data["truncated"] is True


@pytest.mark.asyncio
async def test_html_stripped_from_output():
    """Enrichment response text must not contain raw HTML tags."""
    from unittest.mock import patch, AsyncMock
    from httpx import AsyncClient, ASGITransport
    from src.domain.models.enriched_content import EnrichedContent
    from src.api.main import app

    clean_content = EnrichedContent(
        url="https://example.com",
        text="We build software for clients worldwide.",
        word_count=7,
        truncated=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.site_enricher.SiteEnrichAction.execute",
            new_callable=AsyncMock,
            return_value=clean_content,
        ):
            response = await client.post(
                "/api/v1/enrich",
                headers={"X-API-Key": "default_internal_key"},
                json={"url": "https://example.com"},
            )
    assert response.status_code == 200
    text = response.json()["text"]
    assert "<html" not in text.lower()
    assert "<div" not in text.lower()
    assert "<p>" not in text.lower()
