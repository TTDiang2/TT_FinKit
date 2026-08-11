"""Search backend registry — picks the right backend by name."""
from __future__ import annotations

from typing import Optional

from .base import SearchBackend
from .duckduckgo import DuckDuckGoSearchBackend
from .tavily import TavilySearchBackend


def get_backend(name: str, api_key: Optional[str] = None) -> SearchBackend:
    name = (name or "duckduckgo").lower()
    if name == "duckduckgo":
        return DuckDuckGoSearchBackend()
    if name == "tavily":
        return TavilySearchBackend(api_key=api_key)
    raise ValueError(f"Unknown search backend: {name!r}")
