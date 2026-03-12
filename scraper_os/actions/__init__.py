"""Actions module - реализация команд DSL"""
from .base import BaseAction
from .navigation import (
    GoToAction,
    ClickAction,
    ClickCoordinateAction,
    ScrollAction,
    TypeAction,
    PressKeyAction,
)
from .extraction import (
    ScreenshotAction,
    ExtractHTMLAction,
    ExtractTextAction,
    ExtractMarkdownAction,
    OmniClickAction,
)

__all__ = [
    "BaseAction",
    "GoToAction",
    "ClickAction",
    "ClickCoordinateAction",
    "ScrollAction",
    "TypeAction",
    "PressKeyAction",
    "ScreenshotAction",
    "ExtractHTMLAction",
    "ExtractTextAction",
    "ExtractMarkdownAction",
    "OmniClickAction",
]
