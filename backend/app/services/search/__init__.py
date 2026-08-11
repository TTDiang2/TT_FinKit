"""Search backends for AI investment analysis."""
from .base import SearchBackend, SearchBackendError
from .duckduckgo import DuckDuckGoSearchBackend
from .tavily import TavilySearchBackend
from .registry import get_backend

__all__ = [
    "SearchBackend",
    "SearchBackendError",
    "DuckDuckGoSearchBackend",
    "TavilySearchBackend",
    "get_backend",
]
