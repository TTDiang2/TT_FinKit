"""Search backends for AI investment analysis.

Two impls ship out-of-the-box:
  - DuckDuckGo (keyless, China-accessible) — uses the `ddgs` library
  - Tavily     (optional key, has finance topic filter)

MCP is intentionally NOT used here: MCP servers are for AI clients (Claude
Desktop / Cursor). A FastAPI backend should call the search SDK directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ...schemas.ai_investment import SearchResponse, SearchResult


class SearchBackendError(RuntimeError):
    pass


@dataclass
class SearchBackend(ABC):
    """Abstract search backend. Subclasses implement `search`."""
    name: str = "base"
    api_key: Optional[str] = None

    @abstractmethod
    async def search(self, query: str, max_results: int = 8, days: int = 30) -> SearchResponse:
        """Run a search and return normalized results."""
        ...

    @staticmethod
    def _trim(text: str, max_len: int = 320) -> str:
        if not text:
            return ""
        text = text.strip()
        return text if len(text) <= max_len else text[:max_len].rstrip() + "…"
