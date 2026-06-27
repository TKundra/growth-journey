"""SearchProvider interface + a factory that picks the configured backend.

Keeping search behind one interface means the study-material engine (Phase 2)
never depends on a specific vendor — swap Tavily for DuckDuckGo (or add SerpAPI)
via the SEARCH_PROVIDER env var without touching callers.
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

class SearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """Return ranked results for a query."""
        raise NotImplementedError

@lru_cache
def get_search_provider() -> SearchProvider:
    """Resolve the configured provider, falling back to DuckDuckGo (no key needed)."""
    provider = settings.search_provider.lower()
    if provider == "tavily" and settings.tavily_api_key:
        from app.ai_core.search.tavily import TavilyProvider
        return TavilyProvider()

    # Fallback / default: DuckDuckGo needs no API key.
    from app.ai_core.search.duckduckgo import DuckDuckGoProvider
    return DuckDuckGoProvider()
