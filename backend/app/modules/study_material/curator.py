"""The curation pipeline: search → LLM curate (dedupe, rank, summarize, tag, cite).

Search is resilient and multi-modal: the configured provider (SearXNG by default)
is tried first and we fall back to DuckDuckGo on any error, so a down instance or
over-quota key never blocks the feed. We gather both articles/docs (general web)
and videos (YouTube etc.) so the feed mixes formats. Queries run concurrently to
keep latency flat as the number of angles grows.

Curation is strict: the LLM may only return URLs that appeared in the candidates,
so every item is grounded in a real source (no hallucinated links).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from app.ai_core.llm import get_llm
from app.ai_core.search.base import SearchProvider, SearchResult, get_search_provider
from app.ai_core.search.duckduckgo import DuckDuckGoProvider
from app.core.logging import get_logger
from app.modules.study_material.schemas import CuratedItem, Curation

logger = get_logger(__name__)

# Cap how many resources may share one domain (videos exempt — they're all YouTube),
# so the feed stays varied instead of stacking one publisher.
_MAX_PER_DOMAIN = 3
_MAX_SEARCH_WORKERS = 8
_ALLOWED_KINDS = {"article", "docs", "video", "course", "tutorial", "other"}

_SYSTEM = (
    "You are a learning-resource curator. From a list of web + video search results, "
    "select the best study material for the learner. Deduplicate near-identical results, "
    "rank by usefulness, and write a short why-it-matters summary for each. "
    "Prefer a MIX of formats and reputable sources: include strong video tutorials/playlists "
    "(set their kind to 'video') alongside articles and official docs — don't return only articles. "
    "CRITICAL: only use URLs that appear in the provided candidates — never invent a URL. "
    "Respond with ONLY the JSON object matching the schema — no prose, no markdown, no code fences."
)

def domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:
        return ""


def _search_one(query: str, *, max_results: int, videos: bool = False) -> list[SearchResult]:
    """Run one query through the primary provider, falling back to DuckDuckGo."""
    primary: SearchProvider = get_search_provider()
    run = (
        (lambda p: p.search_videos(query, max_results=max_results))
        if videos
        else (lambda p: p.search(query, max_results=max_results))
    )
    try:
        return run(primary)
    except Exception as exc:  # noqa: BLE001 — any provider failure → fallback
        logger.warning("search provider %s failed (%s); falling back to DDG", primary.name, exc)
        if isinstance(primary, DuckDuckGoProvider):
            return []
        try:
            return run(DuckDuckGoProvider())
        except Exception as exc2:  # noqa: BLE001
            logger.warning("duckduckgo fallback also failed: %s", exc2)
            return []


def gather_candidates(
    article_queries: list[tuple[str, str]],
    video_queries: list[tuple[str, str]] | None = None,
    *,
    per_topic: int,
    per_video: int = 4,
) -> list[dict]:
    """Run all (topic, query) pairs — articles and videos — concurrently and
    flatten to candidate dicts, deduped by URL. Video candidates carry kind=video."""
    video_queries = video_queries or []
    # (topic, query, videos_flag, max_results)
    tasks = [(t, q, False, per_topic) for t, q in article_queries]
    tasks += [(t, q, True, per_video) for t, q in video_queries]
    if not tasks:
        return []

    def _run(task: tuple[str, str, bool, int]) -> tuple[str, list[SearchResult]]:
        topic, query, videos, n = task
        return topic, _search_one(query, max_results=n, videos=videos)

    seen: set[str] = set()
    candidates: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(_MAX_SEARCH_WORKERS, len(tasks))) as pool:
        for topic, results in pool.map(_run, tasks):
            for r in results:
                if not r.url or r.url in seen:
                    continue
                seen.add(r.url)
                candidates.append(
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "topic": topic,
                        "kind": r.kind,  # "video" or None (web)
                    }
                )
    return candidates

def _prompt(candidates: list[dict], *, difficulty: str | None, limit: int) -> str:
    lines = [
        f"Learner difficulty preference: {difficulty or 'unspecified'}.",
        f"Return at most {limit} resources, best first, as the `items` array. "
        "Include a mix of articles, docs, and videos when good ones are present.",
        "Set each item's `kind` to one of: article, docs, video, course, tutorial, other. "
        "Candidates tagged VIDEO are YouTube videos/playlists — set their kind to 'video'.",
        "",
        "Candidates (index. tag title — url — topic — snippet):",
    ]
    for i, c in enumerate(candidates, 1):
        snippet = (c["snippet"] or "")[:300]
        tag = "VIDEO" if c.get("kind") == "video" else "WEB"
        lines.append(f"{i}. {tag} {c['title']} — {c['url']} — [{c['topic']}] — {snippet}")
    return "\n".join(lines)

def _diversify(items: list[CuratedItem]) -> list[CuratedItem]:
    """Cap non-video items per domain so one publisher can't dominate the feed."""
    kept: list[CuratedItem] = []
    per_domain: dict[str, int] = {}
    for item in items:
        if item.kind == "video":
            kept.append(item)
            continue
        d = domain_of(item.url)
        if per_domain.get(d, 0) >= _MAX_PER_DOMAIN:
            continue
        per_domain[d] = per_domain.get(d, 0) + 1
        kept.append(item)
    return kept

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
    # Backfill topic/summary/kind from the originating candidate when the model omits
    # them (it's inconsistent about following the schema's field names). The candidate's
    # kind wins for videos so a YouTube link can't be mislabeled as an article.
    for item in grounded:
        cand = by_url[item.url]
        if cand.get("kind") == "video":
            item.kind = "video"
        elif item.kind not in _ALLOWED_KINDS:
            # model emitted an off-list kind (e.g. echoed a tag) → safe default
            item.kind = "article"
        if not item.topic:
            item.topic = cand.get("topic") or ""
        if not item.summary:
            item.summary = (cand.get("snippet") or "")[:280]
        if not item.title:
            item.title = cand.get("title") or item.url
    return _diversify(grounded)[:limit]
