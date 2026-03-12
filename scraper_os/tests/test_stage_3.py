import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from scraper_os.infrastructure.llm.facade import LLMFacade
from scraper_os.domain.models.dsl import LLMDecision


class TestStage3Integration(unittest.IsolatedAsyncioTestCase):
    @patch("scraper_os.infrastructure.llm.jina_client.httpx.AsyncClient.post")
    @patch("scraper_os.infrastructure.llm.jina_client.httpx.AsyncClient.get")
    async def test_jina_integration(self, mock_get, mock_post):
        facade = LLMFacade()
        # Mock Jina response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={"markdown": "# Test Content", "data": {"price": 100}}
        )
        mock_post.return_value = mock_response

        result = await facade.get_jina_markdown(
            "<html><body>$100</body></html>", {"price": "number"}
        )

        self.assertEqual(result["data"]["price"], 100)

    @patch("scraper_os.infrastructure.llm.openai_client.openai.AsyncOpenAI")
    async def test_openai_decision(self, mock_openai_class):
        # Create the mock client instance before facade is initialized
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_parse = AsyncMock()
        mock_message = MagicMock()
        mock_message.parsed = LLMDecision(
            action="click",
            params={"selector": "button.login"},
            reasoning="Need to login",
        )
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=mock_message)]
        mock_parse.return_value = mock_completion

        # Configure the nested mock
        mock_client.beta = MagicMock()
        mock_client.beta.chat = MagicMock()
        mock_client.beta.chat.completions = MagicMock()
        mock_client.beta.chat.completions.parse = mock_parse

        facade = LLMFacade()
        decision = await facade.decide_next_action(
            dom_tree="<button class='login'>Login</button>",
            objective="Click login button",
            response_model=LLMDecision,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "click")
        self.assertEqual(decision.params["selector"], "button.login")

    @patch("httpx.AsyncClient.post")
    async def test_omni_parser_integration(self, mock_post):
        facade = LLMFacade()
        facade.omni_url = "http://omni-parser:8000/predict"
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={"x": 450, "y": 300, "label": "login_button"}
        )
        mock_post.return_value = mock_response

        coords = await facade.get_omni_coordinates("base64_img", "login button")

        self.assertEqual(coords["x"], 450)
        self.assertEqual(coords["y"], 300)


if __name__ == "__main__":
    unittest.main()
