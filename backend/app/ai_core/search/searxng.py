"""SearXNG search provider — self-hosted metasearch, free, no API key.

SearXNG aggregates many upstream engines (Google, Bing, Brave, Wikipedia, …) and
exposes a JSON API at ``{base}/search?q=…&format=json``. We use the ``general``
category for articles/docs and the ``videos`` category (YouTube etc.) for video
material. Run it via docker-compose (see the repo root); JSON output must be
enabled in its ``settings.yml`` (``search.formats: [html, json]``).
"""

from __future__ import annotations

import httpx

from app.ai_core.search.base import SearchProvider, SearchResult
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class SearxngProvider(SearchProvider):
    name = "searxng"

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or settings.searxng_url or "").rstrip("/")
        if not self._base:
            raise RuntimeError("SEARXNG_URL is not set.")

    def _query(self, query: str, *, categories: str, max_results: int) -> list[dict]:
        resp = httpx.get(
            f"{self._base}/search",
            params={
                "q": query,
                "format": "json",
                "categories": categories,
                "language": "en",
                "safesearch": 1,
            },
            timeout=settings.searxng_timeout,
            headers={"User-Agent": "student-journey/1.0"},
        )
        resp.raise_for_status()
        return (resp.json().get("results") or [])[:max_results]

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", "") or "",
            )
            for r in self._query(query, categories="general", max_results=max_results)
        ]

    def search_videos(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        out: list[SearchResult] = []
        for r in self._query(query, categories="videos", max_results=max_results):
            url = r.get("url", "")
            if not url:
                continue
            # Prefer the human-facing video page; SearXNG sometimes returns extra
            # context (author, length) in `content`.
            out.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("content", "") or "",
                    kind="video",
                )
            )
        return out
