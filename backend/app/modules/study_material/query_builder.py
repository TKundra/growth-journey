"""Turn a learner's profile + preferences into web-search queries.

Pure functions, no I/O — easy to unit-test without a DB or network. The output
is a list of (topic, query) pairs the curator runs through the search provider.
"""

from __future__ import annotations

# Phrase that biases results toward learning material rather than news/marketing.
_LEARN_HINT = "learn tutorial guide"

def _difficulty_hint(difficulty: str | None) -> str:
    return {
        "beginner": "for beginners introduction basics",
        "intermediate": "intermediate practical examples",
        "advanced": "advanced in-depth deep dive",
    }.get(difficulty or "", "")

def resolve_topics(
    *,
    preference_topics: list[str] | None,
    profile: dict | None,
    user_type: str | None,
    overrides: list[str] | None = None,
    max_topics: int = 4,
) -> list[str]:
    """Pick what to study, most specific signal first.

    Priority: explicit overrides → preference topics → profile-derived interests.
    De-duplicated (case-insensitive), trimmed, capped at ``max_topics``.
    """
    # Most specific signal wins outright: explicit overrides replace everything,
    # else preference topics, else fall back to profile-derived interests.
    candidates: list[str] = list(overrides or []) or list(preference_topics or [])

    if not candidates and profile:
        if user_type == "student":
            candidates += profile.get("subjects") or []
            candidates += profile.get("target_exams") or []
            if profile.get("stream"):
                candidates.append(profile["stream"])
        elif user_type == "professional":
            candidates += profile.get("skills") or []
            if profile.get("role"):
                candidates.append(profile["role"])
            if profile.get("industry"):
                candidates.append(profile["industry"])

    seen: set[str] = set()
    topics: list[str] = []
    for raw in candidates:
        t = (raw or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            topics.append(t)
        if len(topics) >= max_topics:
            break
    return topics

# Article angles per topic — broadens recall beyond a single generic query so the
# feed mixes explainers with hands-on practice instead of N near-duplicate hits.
_ARTICLE_ANGLES = (_LEARN_HINT, "examples practice exercises")

def build_queries(topics: list[str], *, difficulty: str | None = None) -> list[tuple[str, str]]:
    """Article search queries as (topic, query) pairs — a few angles per topic."""
    diff = _difficulty_hint(difficulty)
    pairs: list[tuple[str, str]] = []
    for topic in topics:
        for angle in _ARTICLE_ANGLES:
            parts = [topic, angle]
            if diff:
                parts.append(diff)
            pairs.append((topic, " ".join(parts)))
    return pairs

def build_video_queries(topics: list[str]) -> list[tuple[str, str]]:
    """Video search queries as (topic, query) pairs — biased toward full
    tutorials/courses/playlists rather than short clips."""
    return [(topic, f"{topic} tutorial full course playlist") for topic in topics]
