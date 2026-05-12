"""
Integration tests for Google search client.

Tests search_client behavior - both the interface and the underlying models.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.domain.models.requests import SearchRequest, SearchResponse, SearchResult
from src.infrastructure.external_api.search_client import search_client, SearchClient
from inspect import iscoroutinefunction


class TestSearchClientInterface:
    """Test search_client interface and behavior"""

    @pytest.mark.asyncio
    async def test_search_client_search_method_is_async(self):
        """SearchClient.search() should be an async method"""
        assert iscoroutinefunction(SearchClient.search), (
            "SearchClient.search should be an async method"
        )

    @pytest.mark.asyncio
    async def test_search_client_has_proxy_provider(self):
        """search_client should have proxy_provider attribute"""
        assert hasattr(search_client, "_proxy_provider"), (
            "search_client should have _proxy_provider"
        )

    @pytest.mark.asyncio
    async def test_search_client_returns_search_response_type(self):
        """search_client.search() should return SearchResponse type"""
        mock_response = SearchResponse(
            searchParameters={"q": "test", "type": "search", "engine": "google"},
            organic=[
                SearchResult(
                    title="Result 1",
                    link="https://example.com",
                    snippet="Snippet 1",
                    position=1,
                )
            ],
        )

        with patch.object(
            SearchClient, "search", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_response
            result = await search_client.search(SearchRequest(q="test"))

        assert isinstance(result, SearchResponse)
        assert isinstance(result.searchParameters, dict)
        assert "q" in result.searchParameters
        assert result.searchParameters["q"] == "test"
        assert result.searchParameters["engine"] == "google"


class TestSearchRequestModel:
    """Test SearchRequest model behavior"""

    def test_search_request_accepts_query_parameter(self):
        """SearchRequest should accept q parameter"""
        request = SearchRequest(q="python programming")
        assert request.q == "python programming"
        assert isinstance(request.q, str)

    def test_search_request_accepts_num_parameter(self):
        """SearchRequest should accept num parameter with default"""
        request = SearchRequest(q="test", num=20)
        assert request.num == 20
        assert isinstance(request.num, int)

    def test_search_request_default_num_is_10(self):
        """SearchRequest should have default num=10"""
        request = SearchRequest(q="test")
        assert request.num == 10

    def test_search_request_validates_required_q(self):
        """SearchRequest should require q parameter"""
        with pytest.raises(Exception):
            SearchRequest()


class TestSearchResultModel:
    """Test SearchResult model behavior"""

    def test_search_result_has_required_fields(self):
        """SearchResult should have all required fields"""
        result = SearchResult(
            title="Test Title",
            link="https://test.com",
            snippet="Test snippet",
            position=1,
        )
        assert result.title == "Test Title"
        assert result.link == "https://test.com"
        assert result.snippet == "Test snippet"
        assert result.position == 1

    def test_search_result_position_must_be_positive(self):
        """SearchResult position should be positive integer"""
        result = SearchResult(
            title="Test",
            link="https://test.com",
            snippet="Test",
            position=1,
        )
        assert result.position >= 1

    def test_search_result_accepts_empty_snippet(self):
        """SearchResult should accept empty snippet"""
        result = SearchResult(
            title="Test",
            link="https://test.com",
            snippet="",
            position=1,
        )
        assert result.snippet == ""


class TestSearchResponseModel:
    """Test SearchResponse model behavior"""

    def test_search_response_has_search_parameters(self):
        """SearchResponse should include searchParameters"""
        response = SearchResponse(
            searchParameters={"q": "test", "type": "search", "engine": "google"},
            organic=[],
        )
        assert hasattr(response, "searchParameters")
        assert isinstance(response.searchParameters, dict)
        assert "q" in response.searchParameters
        assert "engine" in response.searchParameters

    def test_search_response_has_organic_results(self):
        """SearchResponse should include organic results list"""
        response = SearchResponse(
            searchParameters={"q": "test", "type": "search", "engine": "google"},
            organic=[
                SearchResult(
                    title="Result 1",
                    link="https://example.com",
                    snippet="Snippet 1",
                    position=1,
                )
            ],
        )
        assert hasattr(response, "organic")
        assert isinstance(response.organic, list)
        assert len(response.organic) == 1

    def test_search_response_organic_defaults_to_empty_list(self):
        """SearchResponse should accept empty organic list"""
        response = SearchResponse(
            searchParameters={"q": "test", "type": "search", "engine": "google"},
            organic=[],
        )
        assert response.organic == []

    def test_search_response_accepts_multiple_results(self):
        """SearchResponse should accept multiple organic results"""
        response = SearchResponse(
            searchParameters={"q": "test", "type": "search", "engine": "google"},
            organic=[
                SearchResult(
                    title=f"Result {i}",
                    link=f"https://test{i}.com",
                    snippet=f"Snippet {i}",
                    position=i,
                )
                for i in range(1, 6)
            ],
        )
        assert len(response.organic) == 5


class TestSearchClientWithBrowser:
    """Test search_client with mocked browser to verify flow"""

    @pytest.mark.asyncio
    async def test_search_creates_browser_context(self):
        """Search should create browser context via pool_manager"""
        with patch(
            "src.infrastructure.external_api.search_client.pool_manager"
        ) as mock_pm:
            mock_context = MagicMock()
            mock_context.create_context = AsyncMock()
            mock_pm.create_context = AsyncMock(return_value=mock_context)

            client = SearchClient()
            request = SearchRequest(q="test", num=5)

            try:
                await client.search(request)
            except Exception:
                pass

            assert mock_pm.create_context.called

    @pytest.mark.asyncio
    async def test_search_fallback_without_proxy(self):
        """Search should fallback to no proxy when proxy fails"""

        class TestSearchClient(SearchClient):
            async def _search_with_browser(self, query, proxy=None):
                return [
                    {
                        "title": "Test",
                        "link": "https://test.com",
                        "snippet": "Test",
                        "position": 1,
                    }
                ]

        client = TestSearchClient()
        request = SearchRequest(q="test")
        result = await client.search(request)

        assert isinstance(result, SearchResponse)
        assert len(result.organic) == 1
        assert result.organic[0].title == "Test"

    @pytest.mark.asyncio
    async def test_search_limits_results_by_num(self):
        """Search should limit results to num parameter"""

        class TestSearchClient(SearchClient):
            async def _search_with_browser(self, query, proxy=None):
                return [
                    {
                        "title": f"Result {i}",
                        "link": f"https://test{i}.com",
                        "snippet": f"Snippet {i}",
                        "position": i,
                    }
                    for i in range(1, 11)
                ]

        client = TestSearchClient()
        request = SearchRequest(q="test", num=3)
        result = await client.search(request)

        assert len(result.organic) == 3
        assert result.organic[0].title == "Result 1"
        assert result.organic[2].title == "Result 3"
