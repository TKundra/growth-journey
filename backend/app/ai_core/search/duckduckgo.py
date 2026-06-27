"""DuckDuckGo search provider — no API key required, used as the fallback."""

from __future__ import annotations

from app.ai_core.search.base import SearchProvider, SearchResult

class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            hits = ddgs.text(query, max_results=max_results)
            return [
                SearchResult(
                    title=h.get("title", ""),
                    url=h.get("href", ""),
                    snippet=h.get("body", ""),
                )
                for h in hits
            ]
