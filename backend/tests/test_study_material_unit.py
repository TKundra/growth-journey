"""Phase 2 unit tests — no DB, no network, no LLM.

Covers the pure pieces of the study-material engine: topic resolution priority,
query building, the curation anti-hallucination guardrail, domain parsing, and
RAG chunking.
"""

from __future__ import annotations

from app.ai_core.llm import _extract_json
from app.ai_core.search.base import SearchResult
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


def test_build_queries_includes_difficulty_hint_and_multiple_angles():
    pairs = query_builder.build_queries(["SQL"], difficulty="advanced")
    # one topic → several angles, each carrying the topic + difficulty hint
    assert len(pairs) == len(query_builder._ARTICLE_ANGLES)
    assert all(t == "SQL" for t, _ in pairs)
    assert all("SQL" in q and "advanced" in q for _, q in pairs)
    # the angles are distinct (broader recall, not duplicate queries)
    assert len({q for _, q in pairs}) == len(pairs)


def test_build_video_queries_target_courses_and_playlists():
    pairs = query_builder.build_video_queries(["Calculus", "SQL"])
    assert [t for t, _ in pairs] == ["Calculus", "SQL"]
    assert all("playlist" in q and topic in q for topic, q in pairs)


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


def test_curate_keeps_videos_and_caps_per_domain(monkeypatch):
    # one video + four articles from the SAME domain; the LLM "returns" all of them.
    candidates = [
        {
            "title": "Vid",
            "url": "https://youtube.com/watch?v=1",
            "snippet": "",
            "topic": "x",
            "kind": "video",
        },
        *[
            {
                "title": f"A{i}",
                "url": f"https://blog.dev/{i}",
                "snippet": "",
                "topic": "x",
                "kind": None,
            }
            for i in range(4)
        ],
    ]
    items = [CuratedItem(url=c["url"]) for c in candidates]  # model omits kind on the video
    monkeypatch.setattr(curator, "get_llm", lambda: _FakeLLM(items))
    out = curator.curate(candidates)

    videos = [i for i in out if i.kind == "video"]
    blog = [i for i in out if curator.domain_of(i.url) == "blog.dev"]
    assert len(videos) == 1  # video survived (kind backfilled from candidate)
    assert len(blog) == curator._MAX_PER_DOMAIN  # one publisher capped, not all 4 kept


def test_gather_candidates_runs_both_modalities_and_tags_videos(monkeypatch):
    class _FakeProvider:
        name = "fake"

        def search(self, query, *, max_results=5):
            return [SearchResult(title="Article", url="https://a.dev/x", snippet="s")]

        def search_videos(self, query, *, max_results=5):
            return [
                SearchResult(
                    title="Vid", url="https://youtube.com/watch?v=1", snippet="v", kind="video"
                )
            ]

    monkeypatch.setattr(curator, "get_search_provider", lambda: _FakeProvider())
    cands = curator.gather_candidates(
        [("Topic", "topic learn")], [("Topic", "topic playlist")], per_topic=3
    )
    by_url = {c["url"]: c for c in cands}
    assert by_url["https://a.dev/x"]["kind"] is None  # web article
    assert by_url["https://youtube.com/watch?v=1"]["kind"] == "video"


def test_gather_candidates_dedupes_urls(monkeypatch):
    class _DupProvider:
        name = "dup"

        def search(self, query, *, max_results=5):
            return [SearchResult(title="Same", url="https://same.dev/a", snippet="")]

        def search_videos(self, query, *, max_results=5):
            return []

    monkeypatch.setattr(curator, "get_search_provider", lambda: _DupProvider())
    cands = curator.gather_candidates([("T", "q1"), ("T", "q2")], [], per_topic=3)
    assert len(cands) == 1  # same URL from two queries collapses to one candidate


def test_curate_backfills_missing_topic_and_summary(monkeypatch):
    # Model returns only url+title (omits summary/topic, as gpt-oss does in practice).
    candidates = [
        {
            "title": "K8s Docs",
            "url": "https://kubernetes.io/docs/",
            "snippet": "Official Kubernetes docs.",
            "topic": "Kubernetes",
        }
    ]
    items = [CuratedItem(url="https://kubernetes.io/docs/")]  # no summary/topic/title
    monkeypatch.setattr(curator, "get_llm", lambda: _FakeLLM(items))
    out = curator.curate(candidates)
    assert len(out) == 1
    assert out[0].topic == "Kubernetes"  # backfilled from candidate
    assert out[0].summary == "Official Kubernetes docs."  # backfilled from snippet
    assert out[0].title == "K8s Docs"  # backfilled from candidate


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


# ── SearXNG provider (parsing only — HTTP mocked, no network) ──────────────────
def test_searxng_provider_parses_articles_and_videos(monkeypatch):
    import app.ai_core.search.searxng as sx

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def fake_get(url, params=None, **kwargs):
        if params["categories"] == "videos":
            return _Resp(
                {
                    "results": [
                        {
                            "title": "Course",
                            "url": "https://youtube.com/watch?v=1",
                            "content": "by Chan",
                        }
                    ]
                }
            )
        return _Resp(
            {"results": [{"title": "Guide", "url": "https://a.dev/guide", "content": "a snippet"}]}
        )

    monkeypatch.setattr(sx.httpx, "get", fake_get)
    p = sx.SearxngProvider(base_url="http://searxng:8080/")

    arts = p.search("topic", max_results=3)
    vids = p.search_videos("topic", max_results=3)
    assert arts[0].url == "https://a.dev/guide" and arts[0].kind is None
    assert vids[0].kind == "video" and "youtube.com" in vids[0].url
