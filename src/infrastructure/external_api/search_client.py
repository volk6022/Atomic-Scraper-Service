import httpx
from src.core.config import settings
from src.domain.models.requests import SearchRequest, SearchResponse


class SearchClient:
    def __init__(self):
        self.api_key = settings.ORCHESTRATION_API_KEY  # Or Serper key if used

    async def search(self, request: SearchRequest) -> SearchResponse:
        # Mocking for now, as per Serper compatibility requirement
        return SearchResponse(
            searchParameters={"q": request.q, "type": "search", "engine": "google"},
            organic=[
                {
                    "title": "Example",
                    "link": "https://example.com",
                    "snippet": "Example snippet",
                    "position": 1,
                }
            ],
        )


search_client = SearchClient()
