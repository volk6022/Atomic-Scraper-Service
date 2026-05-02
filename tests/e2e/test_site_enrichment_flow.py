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
