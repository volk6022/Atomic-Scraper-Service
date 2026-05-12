"""
Contract test for Yandex Maps API endpoint.
Tests real endpoint with mocked action (browser automation).
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

TEST_API_KEY = "default_internal_key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


def _mock_business_cards():
    from src.domain.models.business_card import BusinessCard

    return [
        BusinessCard(
            name="Test Restaurant",
            address="Test Street 1",
            phone="+7 123 456 78 90",
            website="https://test.ru",
            geo={"lat": 59.934, "lng": 30.306},
        )
    ]


@pytest.mark.asyncio
async def test_yandex_maps_extraction_returns_200():
    """Yandex Maps extraction endpoint should return 200 OK"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_business_cards(),
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
async def test_yandex_maps_extraction_response_structure():
    """Yandex Maps extraction should return proper response structure"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_business_cards(),
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
        assert "total" in data
        assert "category" in data
        assert "center" in data
        assert "radius" in data
        assert isinstance(data["businesses"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["category"], str)
        assert isinstance(data["center"], dict)
        assert isinstance(data["radius"], int)


@pytest.mark.asyncio
async def test_yandex_maps_business_card_structure():
    """Business card should have required fields"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=_mock_business_cards(),
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
        assert len(data["businesses"]) > 0
        card = data["businesses"][0]
        assert "name" in card
        assert "address" in card
        assert isinstance(card["name"], str)
        assert isinstance(card["address"], str)


@pytest.mark.asyncio
async def test_yandex_maps_business_card_optional_fields():
    """Business card should include optional fields when available"""
    from src.api.main import app
    from src.domain.models.business_card import BusinessCard

    cards_with_extras = [
        BusinessCard(
            name="Test Business",
            address="Test Address",
            phone="+7 999 000 0000",
            website="https://example.com",
            geo={"lat": 59.934, "lng": 30.306},
        )
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=cards_with_extras,
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "cafes",
                    "center": {"lat": 55.7558, "lng": 37.6173},
                    "radius": 500,
                },
            )
        assert response.status_code == 200
        data = response.json()
        card = data["businesses"][0]
        assert "phone" in card
        assert "website" in card
        assert "geo" in card
        assert card["phone"] == "+7 999 000 0000"
        assert card["website"] == "https://example.com"
        assert card["geo"]["lat"] == 59.934
        assert card["geo"]["lng"] == 30.306


@pytest.mark.asyncio
async def test_yandex_maps_empty_results():
    """Yandex Maps extraction should handle empty results"""
    from src.api.main import app
    from src.domain.models.business_card import BusinessCard

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.actions.yandex_maps.YandexMapsExtractAction.execute",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                headers=AUTH_HEADERS,
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 100,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["businesses"] == []
        assert data["total"] == 0


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
async def test_yandex_maps_invalid_latitude():
    """Invalid latitude should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={
                "category": "restaurants",
                "center": {"lat": 999, "lng": 30.306},
                "radius": 1000,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_yandex_maps_invalid_longitude():
    """Invalid longitude should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={
                "category": "restaurants",
                "center": {"lat": 59.934, "lng": 999},
                "radius": 1000,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_yandex_maps_invalid_radius():
    """Invalid radius should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={
                "category": "restaurants",
                "center": {"lat": 59.934, "lng": 30.306},
                "radius": 10000,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_yandex_maps_requires_api_key():
    """Yandex Maps endpoint should require API key - REAL TEST"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            json={
                "category": "restaurants",
                "center": {"lat": 59.934, "lng": 30.306},
                "radius": 1000,
            },
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_yandex_maps_missing_center():
    """Missing center should return 422 validation error"""
    from src.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/yandex-maps/extract",
            headers=AUTH_HEADERS,
            json={
                "category": "restaurants",
                "radius": 1000,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_yandex_maps_category_values():
    """Yandex Maps endpoint should accept various category values"""
    from src.api.main import app
    from src.domain.models.business_card import BusinessCard

    categories = ["restaurants", "cafes", "hotels", "shops", " ATMs"]

    for category in categories:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "src.actions.yandex_maps.YandexMapsExtractAction.execute",
                new_callable=AsyncMock,
                return_value=[BusinessCard(name="Test", address="Addr")],
            ):
                response = await client.post(
                    "/api/v1/yandex-maps/extract",
                    headers=AUTH_HEADERS,
                    json={
                        "category": category,
                        "center": {"lat": 59.934, "lng": 30.306},
                        "radius": 1000,
                    },
                )
            assert response.status_code == 200, f"Failed for category: {category}"
