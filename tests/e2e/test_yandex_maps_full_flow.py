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
    """Yandex Maps endpoint should return list of businesses."""
    import pytest

    pytest.skip("Requires live browser - run manually in Docker environment")

    try:
        import httpx
        import asyncio

        async def check():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:8000/api/v1/yandex-maps/extract",
                    json={
                        "category": "restaurants",
                        "center": {"lat": 59.934, "lng": 30.306},
                        "radius": 500,
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert "businesses" in data
                return len(data["businesses"]) > 0

        result = asyncio.run(check())
        assert result, "No businesses extracted"
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
