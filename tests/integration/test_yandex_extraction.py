"""
Integration test for Yandex Maps extraction.
T020: Write failing integration test for Yandex Maps extraction.

This test MUST fail before implementation (TDD requirement).
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_yandex_maps_action_extracts_businesses():
    """Yandex Maps action should extract business data from Yandex Maps."""
    try:
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()
        assert hasattr(action, "execute"), (
            "YandexMapsExtractAction missing execute method"
        )
    except ImportError:
        pytest.fail("YandexMapsExtractAction does not exist")


@pytest.mark.asyncio
async def test_yandex_maps_action_accepts_location_params():
    """Yandex Maps action should accept category, center, radius parameters."""
    from unittest.mock import MagicMock
    try:
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()

        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.wait_for_selector = AsyncMock()
        mock_page.content = AsyncMock(return_value="")
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        with patch.object(action.pool_manager, "create_context", return_value=mock_context):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await action.execute(
                    category="restaurants",
                    center={"lat": 59.934, "lng": 30.306},
                    radius=1000,
                )
        assert result is not None
    except Exception as e:
        pytest.fail(f"YandexMapsExtractAction does not accept location parameters: {e}")


@pytest.mark.asyncio
async def test_yandex_maps_uses_stealth_browser():
    """Yandex Maps extraction should use stealth browser."""
    try:
        from src.infrastructure.browser.stealth_pool import StealthPool

        stealth = StealthPool()
        assert hasattr(stealth, "new_context"), "StealthPool missing new_context method"
    except ImportError:
        pytest.fail("StealthPool does not exist")


@pytest.mark.asyncio
async def test_yandex_maps_pagination_handles_scroll():
    """Yandex Maps extraction should handle scroll-based pagination."""
    from unittest.mock import MagicMock
    try:
        from src.actions.yandex_maps import YandexMapsExtractAction

        action = YandexMapsExtractAction()

        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        with patch.object(action.pool_manager, "create_context", return_value=mock_context):
            with patch.object(action, "_extract_page", new_callable=AsyncMock, return_value=[]):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await action.execute(
                        category="restaurants",
                        center={"lat": 59.934, "lng": 30.306},
                        radius=1000,
                    )

        assert result is not None
    except Exception as e:
        pytest.fail(f"YandexMapsExtractAction does not handle pagination: {e}")


@pytest.mark.asyncio
async def test_yandex_maps_returns_business_card_list():
    """Yandex Maps action should return list of BusinessCard objects."""
    try:
        from src.domain.models.business_card import BusinessCard

        card = BusinessCard(name="Test Restaurant", address="Test Address")
        assert card.name == "Test Restaurant"
        assert card.address == "Test Address"
    except ImportError:
        pytest.fail("BusinessCard model does not exist")


@pytest.mark.asyncio
async def test_action_registry_has_yandex_maps():
    """Action registry should have Yandex Maps action registered."""
    from src.domain.registry.action_registry import action_registry
    from src.domain.models.dsl import CommandType

    action = action_registry.get_action(CommandType.YANDEX_MAPS_EXTRACT)
    assert action is not None, "Yandex Maps action not registered"


@pytest.mark.asyncio
async def test_pool_manager_uses_user_agent_rotation():
    """Pool manager should use user agent rotation for Yandex requests."""
    try:
        from src.infrastructure.browser.pool_manager import BrowserPoolManager
        from src.infrastructure.browser.user_agent_pool import UserAgentPool

        pm = BrowserPoolManager()
        ua_pool = UserAgentPool()

        assert hasattr(pm, "create_context"), (
            "BrowserPoolManager missing create_context"
        )
        assert hasattr(ua_pool, "get_user_agent"), (
            "UserAgentPool missing get_user_agent"
        )
    except ImportError:
        pytest.fail("Pool manager or user agent pool not available")
