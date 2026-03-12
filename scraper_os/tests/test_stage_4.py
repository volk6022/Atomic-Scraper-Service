import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from scraper_os.domain.registry.action_registry import (
    action_registry,
    ActionRegistry,
    register,
)
from scraper_os.actions.base import BaseAction
from scraper_os.actions.navigation import GotoAction, ClickAction, ScrollAction
from scraper_os.actions.extraction import GetHTMLAction, ScreenshotAction
from scraper_os.actions.ai_actions import (
    OmniClickAction,
    JinaExtractAction,
    SmartStepAction,
)
from scraper_os.domain.models.dsl import ActionResult, LLMDecision


class TestActionRegistry(unittest.TestCase):
    def test_registration(self):
        @register("test_action_unique")
        class TestAction(BaseAction):
            async def execute(self, page, params, llm_facade=None) -> ActionResult:
                return ActionResult.ok("test_action_unique")

        # Note: @register uses the global action_registry singleton
        self.assertTrue(action_registry.has("test_action_unique"))
        self.assertEqual(action_registry.get("test_action_unique"), TestAction)

    def test_duplicate_registration_fails(self):
        registry = ActionRegistry()

        class ActionA(BaseAction):
            async def execute(self, page, params, llm_facade=None) -> ActionResult:
                return ActionResult.ok("dup")

        registry.register("dup", ActionA)
        with self.assertRaises(ValueError):
            registry.register("dup", ActionA)

    def test_unknown_action_fails(self):
        registry = ActionRegistry()
        with self.assertRaises(KeyError):
            registry.get("non_existent")


class TestNavigationActions(unittest.IsolatedAsyncioTestCase):
    async def test_goto_success(self):
        page = AsyncMock()
        page.url = "https://example.com"
        action = GotoAction()
        result = await action.execute(page, {"url": "https://example.com"})

        self.assertEqual(result.status, "ok")
        page.goto.assert_called_once_with(
            "https://example.com", timeout=30000, wait_until="networkidle"
        )

    async def test_click_selector(self):
        page = AsyncMock()
        action = ClickAction()
        await action.execute(page, {"selector": "button#login"})
        page.click.assert_called_once_with("button#login", timeout=10000)

    async def test_click_coords(self):
        page = AsyncMock()
        action = ClickAction()
        await action.execute(page, {"x": 100, "y": 200})
        page.mouse.click.assert_called_once_with(100, 200)


class TestExtractionActions(unittest.IsolatedAsyncioTestCase):
    async def test_get_html(self):
        page = AsyncMock()
        page.content.return_value = "<html></html>"
        action = GetHTMLAction()
        result = await action.execute(page, {})
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data["html"], "<html></html>")

    @patch("scraper_os.actions.base.BaseAction._safe_screenshot")
    async def test_screenshot(self, mock_screenshot):
        mock_screenshot.return_value = "base64data"
        page = AsyncMock()
        action = ScreenshotAction()
        result = await action.execute(page, {})
        self.assertEqual(result.screenshot_base64, "base64data")


class TestAIActions(unittest.IsolatedAsyncioTestCase):
    @patch("scraper_os.actions.base.BaseAction._safe_screenshot")
    async def test_omni_click(self, mock_screenshot):
        mock_screenshot.return_value = "base64img"
        page = AsyncMock()
        llm = AsyncMock()
        llm.get_omni_coordinates.return_value = {"x": 50, "y": 60}

        action = OmniClickAction()
        result = await action.execute(page, {"target": "login"}, llm_facade=llm)

        self.assertEqual(result.status, "ok")
        page.mouse.click.assert_called_once_with(50, 60)

    async def test_jina_extract(self):
        page = AsyncMock()
        page.content.return_value = "<html></html>"
        llm = AsyncMock()
        llm.get_jina_markdown.return_value = {"markdown": "# Test"}

        action = JinaExtractAction()
        result = await action.execute(page, {"schema": {}}, llm_facade=llm)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data["markdown"], "# Test")

    async def test_smart_step(self):
        page = AsyncMock()
        page.content.return_value = "<html></html>"
        llm = AsyncMock()
        llm.decide_next_action.return_value = LLMDecision(
            action="click", params={"selector": "a"}, reasoning="test"
        )

        action = SmartStepAction()
        result = await action.execute(page, {"objective": "find link"}, llm_facade=llm)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data["recommended_action"], "click")


if __name__ == "__main__":
    unittest.main()
