"""Web-search provider abstraction (Tavily primary, DuckDuckGo fallback)."""

from app.ai_core.search.base import SearchProvider, SearchResult, get_search_provider

__all__ = ["SearchProvider", "SearchResult", "get_search_provider"]
