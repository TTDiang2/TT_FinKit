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
                attempts = []
                # DDG news is flaky for narrow/CN queries — fall back through wider tiers
                attempts.append(
                    lambda: list(
                        ddgs.news(
                            query,
                            region="wt-wt",
                            safesearch="off",
                            timelimit=timelimit,
                            max_results=max_results,
                        )
                    )
                )
                attempts.append(
                    lambda: list(
                        ddgs.news(query, region="wt-wt", safesearch="off", max_results=max_results)
                    )
                )
                attempts.append(
                    lambda: list(
                        ddgs.text(query, region="wt-wt", safesearch="off", max_results=max_results)
                    )
                )

                last_err: Exception | None = None
                for attempt in attempts:
                    try:
                        raw = attempt()
                        if raw:
                            return raw
                    except Exception as e:  # noqa: BLE001 — try the next fallback
                        last_err = e
                raise SearchBackendError(
                    f"DuckDuckGo search failed: {last_err or 'No results found.'}"
                ) from last_err

        try:
            raw = await asyncio.to_thread(_do_search)
        except SearchBackendError as e:
            return SearchResponse(query=query, provider=self.name, results=[], error=str(e))

        results: list[SearchResult] = []
        for item in raw:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or item.get("href", "") or "",
                    snippet=self._trim(item.get("body", "") or item.get("description", "") or ""),
                    date=item.get("date", "") or None,
                    source=item.get("source", "") or None,
                )
            )
        return SearchResponse(query=query, provider=self.name, results=results)
