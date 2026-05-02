from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class EnrichedContent(BaseModel):
    url: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    word_count: int = Field(..., ge=0)
    truncated: bool = Field(default=False)
    pages_crawled: Optional[List[str]] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("word_count")
    @classmethod
    def validate_word_count(cls, v: int) -> int:
        if v > 510:
            raise ValueError("word_count should not exceed 510 (truncation required)")
        return v
