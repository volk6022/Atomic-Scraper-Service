import pytest
from src.infrastructure.browser.pool_manager import pool_manager


@pytest.mark.asyncio
async def test_atomic_scrape():
    context = await pool_manager.create_context()
    page = await context.new_page()
    await page.goto("https://example.com")
    content = await page.content()
    assert "<title>Example Domain</title>" in content
    await context.close()
    await pool_manager.close()
