"""Tavily search backend — keyed (free tier 1000/mo) or keyless.

When no API key is provided, the call will fail gracefully and surface a
clear error message so the user can either set a key or switch to DuckDuckGo.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .base import SearchBackend, SearchBackendError
from ...schemas.ai_investment import SearchResponse, SearchResult


class TavilySearchBackend(SearchBackend):
    name = "tavily"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(name=self.name, api_key=api_key)

    async def search(self, query: str, max_results: int = 8, days: int = 30) -> SearchResponse:
        if not self.api_key:
            return SearchResponse(
                query=query,
                provider=self.name,
                results=[],
                error="Tavily requires an API key. Set one in Admin → AI Settings, or switch to DuckDuckGo.",
            )

        def _do_search():
            # Imported lazily so the dependency is only required when actually used
            try:
                from tavily import AsyncTavilyClient
            except ImportError as e:
                raise SearchBackendError(
                    "tavily-python not installed. Run: pip install tavily-python"
                ) from e

            return AsyncTavilyClient(api_key=self.api_key)

        try:
            client = await asyncio.to_thread(_do_search)
            try:
                resp = await client.search(
                    query=query,
                    topic="finance",
                    days=days,
                    max_results=max_results,
                )
            except Exception as e:
                return SearchResponse(query=query, provider=self.name, results=[], error=f"Tavily API error: {e}")
        except SearchBackendError as e:
            return SearchResponse(query=query, provider=self.name, results=[], error=str(e))

        results: list[SearchResult] = []
        for r in resp.get("results", []):
            results.append(
                SearchResult(
                    title=r.get("title", "") or "",
                    url=r.get("url", "") or "",
                    snippet=self._trim(r.get("content", "") or ""),
                    date=r.get("published_date", "") or None,
                    source=(r.get("url") or "").split("/")[2] if "/" in (r.get("url") or "") else None,
                )
            )
        return SearchResponse(query=query, provider=self.name, results=results)
