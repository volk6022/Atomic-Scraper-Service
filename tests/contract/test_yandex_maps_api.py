"""
Contract test for Yandex Maps API endpoint.
T019: Write failing contract test for Yandex Maps API.

This test MUST fail before implementation (TDD requirement).
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

TEST_API_KEY = "default_internal_key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


def _mock_extract():
    from src.domain.models.business_card import BusinessCard
    return [BusinessCard(name="Test Restaurant", address="Test St 1")]


@pytest.mark.asyncio
async def test_yandex_maps_extraction_returns_200():
    """Yandex Maps extraction endpoint should return 200 OK"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_extract(),
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 1000,
                },
            )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_yandex_maps_extraction_response_format():
    """Yandex Maps extraction should return list of business cards"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_extract(),
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 1000,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert "businesses" in data
        assert isinstance(data["businesses"], list)


@pytest.mark.asyncio
async def test_yandex_maps_business_card_structure():
    """Business card should have required fields"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_extract(),
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 1000,
                },
            )
        assert response.status_code == 200
        data = response.json()
        if data["businesses"]:
            card = data["businesses"][0]
            assert "name" in card
            assert "address" in card
            assert isinstance(card["name"], str)
            assert isinstance(card["address"], str)


@pytest.mark.asyncio
async def test_yandex_maps_business_card_optional_fields():
    """Business card should have optional fields when available"""
    from src.api.main import app
    from src.domain.models.business_card import BusinessCard

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=[
                BusinessCard(
                    name="Test",
                    address="Addr",
                    phone="+7 999 000 0000",
                    website="https://example.com",
                    geo={"lat": 59.934, "lng": 30.306},
                )
            ],
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 1000,
                },
            )
        assert response.status_code == 200
        data = response.json()
        if data["businesses"]:
            card = data["businesses"][0]
            if "phone" in card:
                assert isinstance(card["phone"], str)
            if "website" in card:
                assert isinstance(card["website"], str)
            if "geo" in card:
                assert "lat" in card["geo"]
                assert "lng" in card["geo"]


@pytest.mark.asyncio
async def test_yandex_maps_missing_category():
    """Missing category should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={"center": {"lat": 59.934, "lng": 30.306}, "radius": 1000},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_yandex_maps_invalid_coordinates():
    """Invalid coordinates should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={
                "category": "restaurants",
                "center": {"lat": 999, "lng": 999},
                "radius": 1000,
            },
        )
        assert response.status_code == 422
