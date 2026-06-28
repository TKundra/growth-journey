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

    def search_videos(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            hits = ddgs.videos(query, max_results=max_results)
            out: list[SearchResult] = []
            for h in hits:
                # ddgs.videos returns the watch URL under "content".
                url = h.get("content") or h.get("url") or ""
                if not url:
                    continue
                pub = h.get("publisher") or h.get("uploader") or ""
                out.append(
                    SearchResult(
                        title=h.get("title", ""),
                        url=url,
                        snippet=(h.get("description") or pub or ""),
                        kind="video",
                    )
                )
            return out
