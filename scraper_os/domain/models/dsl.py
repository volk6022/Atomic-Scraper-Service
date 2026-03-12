"""
DSL модели - определение команд для управления браузером.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, List


# === Навигация ===
class GoToParams(BaseModel):
    url: str
    wait_until: Literal["domcontentloaded", "load", "networkidle", "commit"] = "domcontentloaded"
    timeout: Optional[int] = None


class ClickParams(BaseModel):
    selector: str
    timeout: Optional[int] = None


class ClickCoordinateParams(BaseModel):
    x: int
    y: int


class ScrollParams(BaseModel):
    direction: Literal["up", "down", "left", "right"] = "down"
    amount: int = 300


class TypeParams(BaseModel):
    selector: str
    text: str
    delay: int = 0


class PressKeyParams(BaseModel):
    key: str


# === Извлечение ===
class ScreenshotParams(BaseModel):
    full_page: bool = False
    quality: int = 80


class ExtractHTMLParams(BaseModel):
    selector: Optional[str] = None


class ExtractTextParams(BaseModel):
    selector: Optional[str] = None


# === AI действия ===
class OmniClickParams(BaseModel):
    target: str = Field(..., description="Что искать на экране (например, 'Login button')")


class ExtractWithJinaParams(BaseModel):
    schema: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON Schema для структурированного извлечения"
    )


class DecideNextParams(BaseModel):
    objective: str = Field(..., description="Цель навигации")


# === Union всех параметров ===
ActionParams = (
    GoToParams | ClickParams | ClickCoordinateParams | ScrollParams |
    TypeParams | PressKeyParams | ScreenshotParams | ExtractHTMLParams |
    ExtractTextParams | OmniClickParams | ExtractWithJinaParams | DecideNextParams
)
