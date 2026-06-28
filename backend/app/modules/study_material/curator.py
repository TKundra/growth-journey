"""The curation pipeline: search → LLM curate (dedupe, rank, summarize, tag, cite).

Search is resilient: the configured provider (Tavily) is tried first and we fall
back to DuckDuckGo on any error so a missing/over-quota key never blocks the feed.
Curation is strict: the LLM may only return URLs that appeared in the candidates,
so every item is grounded in a real source (no hallucinated links).
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.ai_core.llm import get_llm
from app.ai_core.search.base import SearchProvider, SearchResult, get_search_provider
from app.ai_core.search.duckduckgo import DuckDuckGoProvider
from app.core.logging import get_logger
from app.modules.study_material.schemas import CuratedItem, Curation

logger = get_logger(__name__)

_SYSTEM = (
    "You are a learning-resource curator. From a list of web search results, "
    "select the best study material for the learner. Deduplicate near-identical "
    "results, rank by usefulness, and write a short why-it-matters summary for each. "
    "CRITICAL: only use URLs that appear in the provided candidates — never invent a URL. "
    "Respond with ONLY the JSON object matching the schema — no prose, no markdown, no code fences."
)

def domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:
        return ""

def _search_one(query: str, *, max_results: int) -> list[SearchResult]:
    """Run one query through the primary provider, falling back to DuckDuckGo."""
    primary: SearchProvider = get_search_provider()
    try:
        return primary.search(query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 — any provider failure → fallback
        logger.warning("search provider %s failed (%s); falling back to DDG", primary.name, exc)
        if isinstance(primary, DuckDuckGoProvider):
            return []
        try:
            return DuckDuckGoProvider().search(query, max_results=max_results)
        except Exception as exc2:  # noqa: BLE001
            logger.warning("duckduckgo fallback also failed: %s", exc2)
            return []

def gather_candidates(queries: list[tuple[str, str]], *, per_topic: int) -> list[dict]:
    """Run each (topic, query) and flatten to candidate dicts, deduped by URL."""
    seen: set[str] = set()
    candidates: list[dict] = []
    for topic, query in queries:
        for r in _search_one(query, max_results=per_topic):
            if not r.url or r.url in seen:
                continue
            seen.add(r.url)
            candidates.append(
                {"title": r.title, "url": r.url, "snippet": r.snippet, "topic": topic}
            )
    return candidates

def _prompt(candidates: list[dict], *, difficulty: str | None, limit: int) -> str:
    lines = [
        f"Learner difficulty preference: {difficulty or 'unspecified'}.",
        f"Return at most {limit} resources, best first, as the `items` array.",
        "",
        "Candidates (title — url — topic — snippet):",
    ]
    for i, c in enumerate(candidates, 1):
        snippet = (c["snippet"] or "")[:300]
        lines.append(f"{i}. {c['title']} — {c['url']} — [{c['topic']}] — {snippet}")
    return "\n".join(lines)

def curate(
    candidates: list[dict], *, difficulty: str | None = None, limit: int = 12
) -> list[CuratedItem]:
    """LLM-curate candidates into ranked, summarized items grounded in real URLs."""
    if not candidates:
        return []
    by_url = {c["url"]: c for c in candidates}
    result = get_llm().parse(
        _prompt(candidates, difficulty=difficulty, limit=limit),
        Curation,
        tier="default",
        system=_SYSTEM,
    )
    # Guardrail: drop any item whose URL wasn't in the candidate set (anti-hallucination).
    grounded = [item for item in result.items if item.url in by_url]
    dropped = len(result.items) - len(grounded)
    if dropped:
        logger.warning("curate: dropped %d item(s) with non-candidate URLs", dropped)
    # Backfill topic/summary from the originating candidate when the model omits
    # them (it's inconsistent about following the schema's field names).
    for item in grounded:
        cand = by_url[item.url]
        if not item.topic:
            item.topic = cand.get("topic") or ""
        if not item.summary:
            item.summary = (cand.get("snippet") or "")[:280]
        if not item.title:
            item.title = cand.get("title") or item.url
    return grounded[:limit]
