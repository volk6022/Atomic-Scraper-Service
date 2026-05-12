"""
Integration tests for Yandex Maps extraction.

Tests YandexMapsExtractAction behavior and extraction logic.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.domain.models.business_card import BusinessCard


class TestYandexMapsAction:
    """Test YandexMapsExtractAction structure and behavior"""

    @pytest.mark.asyncio
    async def test_yandex_maps_action_has_execute_method(self):
        """YandexMapsExtractAction should have execute method"""
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()
        assert hasattr(action, "execute"), (
            "YandexMapsExtractAction missing execute method"
        )
        assert callable(action.execute)

    @pytest.mark.asyncio
    async def test_yandex_maps_action_has_pool_manager(self):
        """YandexMapsExtractAction should have pool_manager"""
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()
        assert hasattr(action, "pool_manager"), (
            "YandexMapsExtractAction missing pool_manager"
        )

    @pytest.mark.asyncio
    async def test_extraction_handles_empty_results(self):
        """Extraction should handle empty results gracefully"""
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()

        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body></body></html>")
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.locator = MagicMock(
            return_value=MagicMock(all=AsyncMock(return_value=[]))
        )
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        with patch.object(
            action.pool_manager, "create_context", return_value=mock_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch.object(
                    action, "_extract_page", new_callable=AsyncMock, return_value=[]
                ):
                    result = await action.execute(
                        category="cafes",
                        center={"lat": 55.7558, "lng": 37.6173},
                        radius=500,
                    )

        assert result is not None
        assert isinstance(result, list)


class TestBusinessCardModel:
    """Test BusinessCard domain model"""

    def test_business_card_has_required_fields(self):
        """BusinessCard should have required fields"""
        card = BusinessCard(
            name="Test Restaurant",
            address="Test Address 123",
        )
        assert card.name == "Test Restaurant"
        assert card.address == "Test Address 123"

    def test_business_card_has_optional_rating(self):
        """BusinessCard should support optional geo coordinates"""
        from src.domain.models.business_card import GeoCoordinates

        card = BusinessCard(
            name="Test",
            address="Test",
            geo=GeoCoordinates(lat=55.7558, lng=37.6173),
        )
        assert card.geo.lat == 55.7558
        assert card.geo.lng == 37.6173

    def test_business_card_has_optional_phones(self):
        """BusinessCard should support optional phone"""
        card = BusinessCard(
            name="Test",
            address="Test",
            phone="+7-123-456-78-90",
        )
        assert card.phone == "+7-123-456-78-90"

    def test_business_card_has_optional_url(self):
        """BusinessCard should support optional website"""
        card = BusinessCard(
            name="Test",
            address="Test",
            website="https://test.com",
        )
        assert card.website == "https://test.com"


class TestActionRegistry:
    """Test action registry integration"""

    def test_action_registry_has_yandex_maps(self):
        """Action registry should have Yandex Maps action registered"""
        from src.domain.registry.action_registry import action_registry
        from src.domain.models.dsl import CommandType

        action = action_registry.get_action(CommandType.YANDEX_MAPS_EXTRACT)
        assert action is not None, "Yandex Maps action not registered"
        assert callable(action)


class TestStealthPool:
    """Test stealth browser pool"""

    def test_stealth_pool_has_new_context_method(self):
        """StealthPool should have new_context method"""
        from src.infrastructure.browser.stealth_pool import StealthPool

        stealth = StealthPool()
        assert hasattr(stealth, "new_context"), "StealthPool missing new_context method"
        assert callable(stealth.new_context)


class TestPoolManager:
    """Test browser pool manager"""

    def test_pool_manager_has_create_context_method(self):
        """BrowserPoolManager should have create_context method"""
        from src.infrastructure.browser.pool_manager import BrowserPoolManager

        pm = BrowserPoolManager()
        assert hasattr(pm, "create_context"), (
            "BrowserPoolManager missing create_context"
        )

    def test_user_agent_pool_has_get_user_agent_method(self):
        """UserAgentPool should have get_user_agent method"""
        from src.infrastructure.browser.user_agent_pool import UserAgentPool

        ua_pool = UserAgentPool()
        assert hasattr(ua_pool, "get_user_agent"), (
            "UserAgentPool missing get_user_agent"
        )
        user_agent = ua_pool.get_user_agent()
        assert isinstance(user_agent, str)
        assert len(user_agent) > 0


class TestYandexMapsExtractionLogic:
    """Test YandexMapsExtractAction extraction logic with mocks"""

    @pytest.mark.asyncio
    async def test_extraction_returns_list_of_business_cards(self):
        """Extraction should return list of business data"""
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()

        mock_html = """
        <html>
            <div class="search-list">
                <div class="card">
                    <div class="title">Restaurant 1</div>
                    <div class="address">Address 1</div>
                    <div class="rating">4.5</div>
                </div>
            </div>
        </html>
        """

        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.wait_for_selector = AsyncMock()
        mock_page.content = AsyncMock(return_value=mock_html)

        mock_card = MagicMock()
        mock_card.locator = MagicMock(
            return_value=MagicMock(
                first=MagicMock(text_content=AsyncMock(return_value="Test"))
            )
        )

        mock_page.locator = MagicMock(
            return_value=MagicMock(all=AsyncMock(return_value=[mock_card]))
        )

        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        with patch.object(
            action.pool_manager, "create_context", return_value=mock_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await action.execute(
                    category="restaurants",
                    center={"lat": 59.934, "lng": 30.306},
                    radius=1000,
                )

        assert result is not None
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_extraction_handles_empty_results(self):
        """Extraction should handle empty results gracefully"""
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()

        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body></body></html>")
        mock_page.locator = MagicMock(
            return_value=MagicMock(all=AsyncMock(return_value=[]))
        )
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        with patch.object(
            action.pool_manager, "create_context", return_value=mock_context
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await action.execute(
                    category="cafes",
                    center={"lat": 55.7558, "lng": 37.6173},
                    radius=500,
                )

        assert result is not None
        assert isinstance(result, list)


class TestYandexMapsRouter:
    """Test Yandex Maps router endpoint"""

    @pytest.mark.asyncio
    async def test_yandex_maps_endpoint_exists(self):
        """API should have yandex-maps extract endpoint"""
        from httpx import AsyncClient, ASGITransport
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
                headers={"X-API-Key": "default_internal_key"},
            )
            assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_yandex_maps_validates_geo_center(self):
        """Yandex Maps endpoint should validate geo center coordinates"""
        from httpx import AsyncClient, ASGITransport
        from src.api.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                json={
                    "category": "restaurants",
                    "center": {"lat": 999, "lng": 30.306},
                    "radius": 1000,
                },
                headers={"X-API-Key": "default_internal_key"},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_yandex_maps_validates_radius(self):
        """Yandex Maps endpoint should validate radius range"""
        from httpx import AsyncClient, ASGITransport
        from src.api.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/yandex-maps/extract",
                json={
                    "category": "restaurants",
                    "center": {"lat": 59.934, "lng": 30.306},
                    "radius": 99999,
                },
                headers={"X-API-Key": "default_internal_key"},
            )
            assert response.status_code == 422
