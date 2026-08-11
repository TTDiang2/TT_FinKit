"""DuckDuckGo News search via the `ddgs` library — keyless + China-friendly."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from .base import SearchBackend, SearchBackendError
from ...schemas.ai_investment import SearchResponse, SearchResult


class DuckDuckGoSearchBackend(SearchBackend):
    name = "duckduckgo"

    def __init__(self, api_key: Optional[str] = None):
        # api_key ignored — DDG is keyless
        super().__init__(name=self.name, api_key=None)

    async def search(self, query: str, max_results: int = 8, days: int = 30) -> SearchResponse:
        # `ddgs` is sync — run in a threadpool
        def _do_search():
            # Imported lazily so the dependency is only required when actually used
            from ddgs import DDGS

            timelimit = "m" if days >= 30 else ("w" if days >= 7 else "d")
            with DDGS() as ddgs:
                try:
                    raw = list(
                        ddgs.news(
                            keywords=query,
                            region="wt-wt",
                            safesearch="off",
                            timelimit=timelimit,
                            max_results=max_results,
                        )
                    )
                except Exception as e:
                    raise SearchBackendError(f"DuckDuckGo search failed: {e}") from e
            return raw

        try:
            raw = await asyncio.to_thread(_do_search)
        except SearchBackendError as e:
            return SearchResponse(query=query, provider=self.name, results=[], error=str(e))

        results: list[SearchResult] = []
        for item in raw:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=self._trim(item.get("body", "") or ""),
                    date=item.get("date", "") or None,
                    source=item.get("source", "") or None,
                )
            )
        return SearchResponse(query=query, provider=self.name, results=results)
