from enum import Enum
from typing import List, Literal, Optional
import uuid

from pydantic import BaseModel, Field, HttpUrl

from src.domain.models.yandex_organization import YandexOrganization
from src.domain.models.yandex_review import YandexReview


class TaskStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class ScrapeRequest(BaseModel):
    url: HttpUrl
    proxy: Optional[str] = None
    wait_until: Optional[str] = "domcontentloaded"
    clean_html: bool = False
    output_format: Literal["html", "text", "markdown"] = "html"


class ScrapeResponse(BaseModel):
    id: str = str(uuid.uuid4())
    url: str
    content: Optional[str] = None
    status: TaskStatus
    error: Optional[str] = None


class SearchRequest(BaseModel):
    q: str
    num: int = Field(default=10, ge=1, le=100)


class SearchResult(BaseModel):
    title: str
    link: str
    snippet: str
    position: int


class SearchResponse(BaseModel):
    searchParameters: dict
    organic: List[SearchResult]


class OmniParseRequest(BaseModel):
    base64_image: str
    prompt: Optional[str] = None


class HtmlToMdRequest(BaseModel):
    html: str
    format: str = "markdown"
    extraction_schema: Optional[dict] = None


# -----------------------------------------------------------------------------
# Yandex Maps — text + region search (XHR-intercept approach, see
# `docs/yandex-maps-scraping-experiment-journal.md`).
# -----------------------------------------------------------------------------


class YandexMapsExtractRequest(BaseModel):
    """Search Yandex Maps for organizations by text query within a region."""

    query: str = Field(..., min_length=1, max_length=200, description="напр. 'стоматология'")
    region_id: int = Field(
        2, ge=1, description="Yandex `lr=` region id (2 = SPB, 213 = Moscow)"
    )
    city_slug: str = Field(
        "saint-petersburg",
        min_length=1,
        max_length=100,
        description="URL slug used in `/maps/{region_id}/{city_slug}/search/...`",
    )
    target_count: int = Field(
        40, ge=1, le=200, description="Stop once N unique organizations are collected"
    )
    include_raw: bool = Field(
        True, description="Whether to include the upstream `raw` JSON per org in the response"
    )


class YandexMapsExtractResponse(BaseModel):
    organizations: list[YandexOrganization]
    total: int
    query: str
    region_id: int


class YandexMapsReviewsRequest(BaseModel):
    """Fetch reviews for a single organization via `fetchReviews` replay."""

    business_oid: str = Field(..., pattern=r"^\d+$", description="Yandex business id")
    seoname: str = Field(..., min_length=1, max_length=200, description="URL slug")
    count: int = Field(50, ge=1, le=200, description="Reviews per page (Yandex internal cap ~50)")
    ranking: Literal["by_time", "by_rating"] = "by_time"
    pages: int = Field(1, ge=1, le=10, description="Number of scroll-driven pages to collect")
    include_raw: bool = Field(True, description="Whether to keep the upstream raw JSON per review")


class YandexMapsReviewsResponse(BaseModel):
    reviews: list[YandexReview]
    total: int
    business_oid: str


class EnrichRequest(BaseModel):
    url: HttpUrl
    crawl_about: bool = False
    crawl_services: bool = False


class EnrichResponse(BaseModel):
    url: str
    text: str
    word_count: int
    truncated: bool
    pages_crawled: Optional[List[str]] = None
