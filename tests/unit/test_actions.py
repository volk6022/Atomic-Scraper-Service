import pytest
import asyncio
from src.actions.navigation import goto_action
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_goto_action():
    page = MagicMock()
    page.goto = MagicMock(return_value=asyncio.Future())
    page.goto.return_value.set_result(None)

    result = await goto_action(page, {"url": "https://example.com"})
    assert result["status"] == "success"
