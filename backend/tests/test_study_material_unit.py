"""Phase 2 unit tests — no DB, no network, no LLM.

Covers the pure pieces of the study-material engine: topic resolution priority,
query building, the curation anti-hallucination guardrail, domain parsing, and
RAG chunking.
"""

from __future__ import annotations

from app.ai_core.llm import _extract_json
from app.modules.study_material import curator, query_builder, rag
from app.modules.study_material.schemas import Curation, CuratedItem


# ── query builder ─────────────────────────────────────────────────────────────
def test_resolve_topics_priority_overrides_then_prefs_then_profile():
    profile = {"skills": ["docker"], "role": "SRE"}
    # overrides win outright (replace prefs + profile)
    assert query_builder.resolve_topics(
        preference_topics=["python"],
        profile=profile,
        user_type="professional",
        overrides=["kubernetes"],
    ) == ["kubernetes"]
    # then preference topics
    assert query_builder.resolve_topics(
        preference_topics=["python"],
        profile=profile,
        user_type="professional",
    ) == ["python"]
    # then profile-derived (skills/role) when nothing else is set
    assert query_builder.resolve_topics(
        preference_topics=[],
        profile=profile,
        user_type="professional",
    ) == ["docker", "SRE"]


def test_resolve_topics_dedupes_and_caps():
    out = query_builder.resolve_topics(
        preference_topics=["Python", "python ", "SQL", "Go", "Rust"],
        profile=None,
        user_type="student",
        max_topics=3,
    )
    assert out == ["Python", "SQL", "Go"]  # case-insensitive dedupe, capped at 3


def test_student_profile_fallback_uses_subjects_and_exams():
    out = query_builder.resolve_topics(
        preference_topics=None,
        profile={"subjects": ["Calculus"], "target_exams": ["JEE"], "stream": "Science"},
        user_type="student",
    )
    assert out == ["Calculus", "JEE", "Science"]


def test_build_queries_includes_difficulty_hint():
    pairs = query_builder.build_queries(["SQL"], difficulty="advanced")
    assert pairs[0][0] == "SQL"
    assert "SQL" in pairs[0][1] and "advanced" in pairs[0][1]


# ── curation guardrail ────────────────────────────────────────────────────────
class _FakeLLM:
    def __init__(self, items):
        self._items = items

    def parse(self, *_args, **_kwargs):
        return Curation(items=self._items)


def test_curate_drops_non_candidate_urls(monkeypatch):
    candidates = [{"title": "Real", "url": "https://real.dev/a", "snippet": "", "topic": "x"}]
    items = [
        CuratedItem(title="Real", url="https://real.dev/a", summary="ok", topic="x"),
        CuratedItem(title="Fake", url="https://hallucinated.example/z", summary="no", topic="x"),
    ]
    monkeypatch.setattr(curator, "get_llm", lambda: _FakeLLM(items))
    out = curator.curate(candidates)
    assert [i.url for i in out] == ["https://real.dev/a"]  # invented URL removed


def test_curate_empty_candidates_short_circuits():
    assert curator.curate([]) == []


def test_curate_backfills_missing_topic_and_summary(monkeypatch):
    # Model returns only url+title (omits summary/topic, as gpt-oss does in practice).
    candidates = [
        {"title": "K8s Docs", "url": "https://kubernetes.io/docs/",
         "snippet": "Official Kubernetes docs.", "topic": "Kubernetes"}
    ]
    items = [CuratedItem(url="https://kubernetes.io/docs/")]  # no summary/topic/title
    monkeypatch.setattr(curator, "get_llm", lambda: _FakeLLM(items))
    out = curator.curate(candidates)
    assert len(out) == 1
    assert out[0].topic == "Kubernetes"                 # backfilled from candidate
    assert out[0].summary == "Official Kubernetes docs."  # backfilled from snippet
    assert out[0].title == "K8s Docs"                   # backfilled from candidate


# ── parse() JSON extraction fallback (models that wrap JSON in prose/fences) ───
def test_extract_json_from_fenced_block_with_prose():
    chatty = (
        "**Recommended intermediate resources**\n\nHere you go:\n\n"
        '```json\n{"items": [{"title": "K8s", "url": "https://kubernetes.io/docs/",'
        ' "summary": "Official docs.", "topic": "Kubernetes"}]}\n```'
    )
    extracted = _extract_json(chatty)
    obj = Curation.model_validate_json(extracted)
    assert obj.items[0].url == "https://kubernetes.io/docs/"


def test_extract_json_from_bare_prose():
    assert _extract_json('Sure!\n{"items": []}\nHope that helps.') == '{"items": []}'


def test_extract_json_returns_none_when_absent():
    assert _extract_json("no json here at all") is None
    assert _extract_json("") is None


def test_domain_of_strips_www():
    assert curator.domain_of("https://www.sqlbolt.com/lesson") == "sqlbolt.com"
    assert curator.domain_of("https://docs.python.org/3/") == "docs.python.org"


# ── RAG chunking ──────────────────────────────────────────────────────────────
def test_chunk_text_short_returns_single_chunk():
    assert rag.chunk_text("a short note") == ["a short note"]


def test_chunk_text_splits_long_text_with_overlap():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = rag.chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
