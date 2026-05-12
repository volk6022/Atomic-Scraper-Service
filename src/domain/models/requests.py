from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Literal
from enum import Enum
import uuid


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


class GeoCenter(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class YandexMapsExtractRequest(BaseModel):
    category: str
    center: GeoCenter
    radius: int = Field(..., ge=100, le=5000)


class YandexMapsExtractResponse(BaseModel):
    businesses: list
    total: int
    category: str
    center: dict
    radius: int


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
