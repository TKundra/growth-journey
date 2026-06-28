"""SearchProvider interface + a factory that picks the configured backend.

Keeping search behind one interface means the study-material engine (Phase 2)
never depends on a specific vendor — swap SearXNG / Tavily / DuckDuckGo (or add
SerpAPI) via the SEARCH_PROVIDER env var without touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pydantic import BaseModel

from app.core.config import settings

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    # Modality hint set by the provider. None = generic web (article/docs), which
    # the curator's LLM classifies; "video" is set by video search so YouTube
    # videos/playlists keep their kind through curation.
    kind: str | None = None

class SearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Return ranked general web results for a query."""
        raise NotImplementedError

    def search_videos(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Return video results (YouTube etc.). Providers that can't do video
        leave this as a no-op so the curator simply gets no video candidates."""
        return []

@lru_cache
def get_search_provider() -> SearchProvider:
    """Resolve the configured provider, falling back to DuckDuckGo (no key needed)."""
    provider = settings.search_provider.lower()
    if provider == "searxng" and settings.searxng_url:
        from app.ai_core.search.searxng import SearxngProvider
        return SearxngProvider()
    
    if provider == "tavily" and settings.tavily_api_key:
        from app.ai_core.search.tavily import TavilyProvider
        return TavilyProvider()

    # Fallback / default: DuckDuckGo needs no API key.
    from app.ai_core.search.duckduckgo import DuckDuckGoProvider
    return DuckDuckGoProvider()
