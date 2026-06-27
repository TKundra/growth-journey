"""Tavily search provider (best results for LLM consumption)."""

from __future__ import annotations

from app.ai_core.search.base import SearchProvider, SearchResult
from app.core.config import settings

class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self) -> None:
        from tavily import TavilyClient

        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is not set.")
        self._client = TavilyClient(api_key=settings.tavily_api_key)

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        resp = self._client.search(query=query, max_results=max_results)
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in resp.get("results", [])
        ]
