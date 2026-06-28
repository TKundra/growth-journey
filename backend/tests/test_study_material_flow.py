"""Phase 2 integration test: generate → feed → save → library → unsave.

Search and LLM curation are monkeypatched (no network, no API key needed) so
this exercises the real routes + SQL: dedupe, is_saved flagging, library join.
Requires a database with migrations applied; skipped otherwise (see conftest).
"""

from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.study_material import curator
from app.modules.study_material.schemas import CuratedItem
from tests.conftest import requires_db

client = TestClient(app)


def _signup_with_prefs(topics):
    email = f"pytest_sm_{uuid4().hex[:10]}@example.com"
    client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = client.post("/auth/login", json={"email": email, "password": "secret123"}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        "/preferences/me", headers=headers, json={"topics": topics, "difficulty": "beginner"}
    )
    return headers


_FAKE_ITEMS = [
    CuratedItem(
        title="Python Tutorial",
        url="https://docs.python.org/3/tutorial/",
        summary="The official tutorial.",
        topic="Python",
        tags=["python"],
        difficulty="beginner",
        kind="docs",
        est_minutes=120,
        relevance=95,
    ),
    CuratedItem(
        title="SQLBolt",
        url="https://sqlbolt.com/",
        summary="Interactive SQL.",
        topic="SQL",
        tags=["sql"],
        difficulty="beginner",
        kind="tutorial",
        est_minutes=60,
        relevance=88,
    ),
]


@pytest.fixture
def _stub_pipeline(monkeypatch):
    monkeypatch.setattr(
        curator,
        "gather_candidates",
        lambda article_queries, video_queries=None, *, per_topic, per_video=4: [
            {"title": "c", "url": i.url, "snippet": "", "topic": i.topic, "kind": None}
            for i in _FAKE_ITEMS
        ],
    )
    monkeypatch.setattr(curator, "curate", lambda candidates, **kw: list(_FAKE_ITEMS))


@requires_db
def test_generate_requires_topics():
    headers = _signup_with_prefs([])  # no topics, student type unset → nothing to study
    r = client.post("/study-material/generate", headers=headers, json={})
    assert r.status_code == 422


@requires_db
def test_full_study_flow(_stub_pipeline):
    headers = _signup_with_prefs(["Python", "SQL"])

    # generate the feed
    r = client.post("/study-material/generate", headers=headers, json={})
    assert r.status_code == 200
    assert r.json()["generated"] == 2

    # re-running dedupes (same URLs) — still 2 in the feed
    client.post("/study-material/generate", headers=headers, json={})
    feed = client.get("/study-material", headers=headers).json()
    assert len(feed) == 2
    assert all(not r["is_saved"] for r in feed)
    # ranked by relevance desc
    assert feed[0]["relevance"] >= feed[1]["relevance"]
    assert feed[0]["source_domain"] == "docs.python.org"

    # save the top resource → library has it, feed flag flips
    pid = feed[0]["public_id"]
    r = client.post(f"/study-material/{pid}/save", headers=headers, json={"note": "start here"})
    assert r.status_code == 200 and r.json()["note"] == "start here"

    library = client.get("/study-material/library", headers=headers).json()
    assert len(library) == 1 and library[0]["resource"]["public_id"] == pid

    feed2 = client.get("/study-material", headers=headers).json()
    assert next(x for x in feed2 if x["public_id"] == pid)["is_saved"] is True

    # unsave → library empties
    assert client.delete(f"/study-material/{pid}/save", headers=headers).status_code == 204
    assert client.get("/study-material/library", headers=headers).json() == []

    # unknown resource id → 404
    assert (
        client.post(f"/study-material/{uuid4()}/save", headers=headers, json={}).status_code == 404
    )


@requires_db
def test_resources_are_shared_across_users(_stub_pipeline):
    """Two users curating the same URLs share ONE canonical resource row (no
    per-user duplication), while each keeps their own feed entry + public_id."""
    urls = tuple(i.url for i in _FAKE_ITEMS)

    def _canonical_count():
        with psycopg.connect(settings.database_url) as conn:
            return conn.execute(
                "select count(*) from resources where url = any(%s)", (list(urls),)
            ).fetchone()[0]

    headers_a = _signup_with_prefs(["Python", "SQL"])
    client.post("/study-material/generate", headers=headers_a, json={})
    after_a = _canonical_count()

    headers_b = _signup_with_prefs(["Python", "SQL"])
    client.post("/study-material/generate", headers=headers_b, json={})
    after_b = _canonical_count()

    # User B reused A's canonical rows — the count didn't grow.
    assert after_a == len(_FAKE_ITEMS)
    assert after_b == after_a

    # Both users see the same canonical public_id for the same URL...
    feed_a = {
        r["url"]: r["public_id"] for r in client.get("/study-material", headers=headers_a).json()
    }
    feed_b = {
        r["url"]: r["public_id"] for r in client.get("/study-material", headers=headers_b).json()
    }
    assert feed_a == feed_b
    # ...yet each has their own feed entry (both see all items).
    assert len(feed_a) == len(_FAKE_ITEMS)
