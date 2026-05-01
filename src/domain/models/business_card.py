from pydantic import BaseModel, Field, field_validator
from typing import Optional


class GeoCoordinates(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class BusinessCard(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    address: str = Field(..., min_length=1, max_length=1000)
    phone: Optional[str] = None
    website: Optional[str] = None
    geo: Optional[GeoCoordinates] = None
    category: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            digits = "".join(c for c in v if c.isdigit())
            if len(digits) < 7:
                raise ValueError("Phone must have at least 7 digits")
        return v

    @field_validator("website")
    @classmethod
    def validate_website(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith(("http://", "https://")):
            return f"https://{v}"
        return v
