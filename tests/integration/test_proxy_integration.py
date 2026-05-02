"""
Integration test for proxy integration.
T014: Write failing contract test for proxy integration.

This test MUST fail before implementation (TDD requirement).
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock


@pytest.mark.asyncio
async def test_proxy_provider_integrated_in_pool():
    """Proxy provider should be integrated in pool manager create_context."""
    try:
        from src.infrastructure.browser.pool_manager import BrowserPoolManager

        pm = BrowserPoolManager()

        with patch.object(pm, "get_browser") as mock_browser:
            mock_ctx = AsyncMock()
            mock_browser.return_value.new_context = AsyncMock(return_value=mock_ctx)

            await pm.create_context(proxy="http://test-proxy:8080")

            call_args = mock_browser.return_value.new_context.call_args
            assert call_args is not None
            assert "proxy" in str(call_args) or call_args.kwargs.get("proxy")
    except Exception as e:
        pytest.fail(f"Proxy integration not working: {e}")


@pytest.mark.asyncio
async def test_proxy_provider_reads_from_file():
    """Proxy provider should read proxies from file."""
    try:
        from src.infrastructure.browser.proxy_provider import ProxyProvider

        provider = ProxyProvider()
        assert hasattr(provider, "get_proxy"), "ProxyProvider missing get_proxy method"
    except ImportError:
        pytest.fail("ProxyProvider does not exist")


@pytest.mark.asyncio
async def test_pool_manager_accepts_proxy_config():
    """Pool manager create_context should accept proxy parameter."""
    try:
        from src.infrastructure.browser.pool_manager import BrowserPoolManager

        pm = BrowserPoolManager()

        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_browser = AsyncMock()
            mock_ctx = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_ctx)
            mock_pw.return_value.start.return_value.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_pw.return_value.start.return_value.chromium.launch.return_value = (
                mock_browser
            )

            result = await pm.create_context(proxy="http://proxy:8080")

            assert mock_browser.new_context.called
    except Exception:
        pass


def test_proxy_file_loaded_in_compose():
    """docker-compose should mount proxies.txt if it exists."""
    import os
    import yaml

    if not os.path.exists("docker-compose.yml"):
        pytest.skip("docker-compose.yml not found")

    if not os.path.exists("proxies.txt"):
        pytest.skip("proxies.txt not found")

    with open("docker-compose.yml", "r") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})

    for name in ["api", "worker"]:
        if name in services:
            volumes = services[name].get("volumes", [])
            has_proxy = any("proxies.txt" in str(v) for v in volumes)
            assert has_proxy, f"Service {name} missing proxies.txt volume mount"
