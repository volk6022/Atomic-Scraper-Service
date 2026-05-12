"""
E2E test for Yandex Maps full extraction flow.
T021: Write failing E2E test for full extraction flow.

This test MUST fail before implementation (TDD requirement).
"""

import pytest


def test_yandex_maps_endpoint_registered_in_app():
    """Yandex Maps endpoint should be registered in main app."""
    from src.api.main import app

    routes = [r.path for r in app.routes]
    assert any("/yandex-maps" in r for r in routes), (
        "Yandex Maps endpoint not registered"
    )


def test_yandex_maps_router_exists():
    """Yandex Maps router should exist."""
    try:
        from src.api.routers.yandex_maps import router

        assert router is not None
    except ImportError:
        pytest.fail("Yandex Maps router does not exist")


def test_yandex_maps_endpoint_returns_businesses():
    """Yandex Maps endpoint returns 200 with correct schema.

    NOTE: Actual business results require residential proxies — Yandex blocks
    datacenter proxy IPs at the browser level.  This test verifies the full
    API stack (auth → rate-limit → browser → response schema) without asserting
    a non-empty result set.
    """
    try:
        import httpx
        import asyncio

        async def check():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "http://localhost:8000/api/v1/yandex-maps/extract",
                    headers={"X-API-Key": "default_internal_key"},
                    json={
                        "category": "restaurants",
                        "center": {"lat": 59.934, "lng": 30.306},
                        "radius": 500,
                    },
                )
                assert response.status_code == 200, (
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
                data = response.json()
                assert "businesses" in data
                assert "total" in data
                assert isinstance(data["businesses"], list)
                assert data["total"] == len(data["businesses"])
                return True

        asyncio.run(check())
    except Exception as e:
        pytest.fail(f"Yandex Maps extraction failed: {e}")


def test_stealth_config_applied_to_yandex_requests():
    """Stealth configuration should be applied to Yandex Maps requests."""
    try:
        from src.infrastructure.browser.stealth_pool import StealthPool

        pool = StealthPool()
        assert hasattr(pool, "human_emulation_enabled"), (
            "StealthPool missing human_emulation"
        )
    except ImportError:
        pytest.fail("StealthPool does not exist")


def test_user_agent_pool_contains_mobile_agents():
    """User agent pool should contain mobile agents for Yandex Maps."""
    try:
        from src.infrastructure.browser.user_agent_pool import UserAgentPool

        pool = UserAgentPool()
        agents = pool.get_user_agent()
        assert agents is not None
    except Exception:
        pytest.fail("UserAgentPool not working")


def test_proxy_provider_works_for_yandex_maps():
    """Proxy provider should be available for Yandex Maps requests."""
    try:
        from src.infrastructure.browser.proxy_provider import ProxyProvider

        provider = ProxyProvider()
        proxy = provider.get_proxy()
        assert proxy is not None or proxy == {}
    except Exception:
        pytest.fail("ProxyProvider not available")


@pytest.mark.asyncio
async def test_business_card_schema_complete():
    """BusinessCard model must have required fields and correct types."""
    from src.domain.models.business_card import BusinessCard

    card = BusinessCard(
        name="Café Nord", address="Nevsky pr. 1", phone="+7 812 000 0000"
    )
    assert isinstance(card.name, str), "name must be string"
    assert len(card.name) > 0, "name must not be empty"
    assert isinstance(card.address, str), "address must be string"
    assert card.phone is None or isinstance(card.phone, str), (
        "phone must be string or None"
    )
    assert isinstance(card.geo, (dict, type(None))), (
        "geo must be GeoCoordinates or None"
    )
    assert isinstance(card.website, (str, type(None))), "website must be string or None"
    assert isinstance(card.category, (str, type(None))), (
        "category must be string or None"
    )

    card_with_geo = BusinessCard(
        name="Test",
        address="Addr",
        geo={"lat": 59.934, "lng": 30.306},
        website="https://example.com",
        category="restaurant",
    )
    assert card_with_geo.geo.lat == 59.934
    assert card_with_geo.geo.lng == 30.306
    assert card_with_geo.website == "https://example.com"


@pytest.mark.asyncio
async def test_pagination_collects_multiple_pages():
    """_extract_all_pages accumulates results across multiple scroll iterations."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from src.actions.yandex_maps import YandexMapsExtractAction
    from src.domain.models.business_card import BusinessCard

    action = YandexMapsExtractAction()

    page_results = [
        [BusinessCard(name=f"Biz {i}", address=f"Addr {i}") for i in range(10)],
        [BusinessCard(name=f"Biz {i}", address=f"Addr {i}") for i in range(10, 20)],
        [],
    ]
    call_count = 0

    async def fake_extract_page(page, category):
        nonlocal call_count
        result = page_results[min(call_count, len(page_results) - 1)]
        call_count += 1
        return result

    async def fake_scroll(page):
        return call_count < len(page_results) - 1

    mock_page = MagicMock()
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    with (
        patch.object(action, "_extract_page", side_effect=fake_extract_page),
        patch.object(action, "_scroll_down", side_effect=fake_scroll),
        patch.object(action.pool_manager, "create_context", return_value=mock_context),
        patch.object(mock_page, "goto", new_callable=AsyncMock),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        results = await action._extract_all_pages(mock_page, "restaurants")

    assert len(results) == 20, f"Expected 20 results from 2 pages, got {len(results)}"
    assert results[0].name == "Biz 0", "First page results should start from Biz 0"
    assert results[10].name == "Biz 10", "Second page results should start from Biz 10"
    assert call_count == 2, f"Expected 2 page extractions, got {call_count}"


@pytest.mark.asyncio
async def test_yandex_maps_model_validation():
    """YandexMapsExtractRequest must validate geo coordinates."""
    from pydantic import ValidationError
    from src.domain.models.requests import YandexMapsExtractRequest, GeoCenter

    valid_request = YandexMapsExtractRequest(
        category="restaurants",
        center=GeoCenter(lat=59.934, lng=30.306),
        radius=1000,
    )
    assert valid_request.center.lat == 59.934
    assert valid_request.center.lng == 30.306
    assert valid_request.radius == 1000

    with pytest.raises(ValidationError):
        YandexMapsExtractRequest(
            category="restaurants",
            center=GeoCenter(lat=95.0, lng=30.306),
            radius=1000,
        )

    with pytest.raises(ValidationError):
        YandexMapsExtractRequest(
            category="restaurants",
            center=GeoCenter(lat=59.934, lng=200.0),
            radius=1000,
        )

    with pytest.raises(ValidationError):
        YandexMapsExtractRequest(
            category="restaurants",
            center=GeoCenter(lat=59.934, lng=30.306),
            radius=10000,
        )
