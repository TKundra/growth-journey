"""Phase 6 integration tests: formal mock tests — auto + explicit sectional
generation, the timed taker view, single-submission scoring, and the detailed
report (section scores, percentile, time analysis, weak areas, next steps).

Generation is monkeypatched (no live LLM); everything else hits the real routes
and SQL. Requires a migrated database; skipped otherwise.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.assessments import generator as gen_mod
from app.modules.assessments.schemas import GeneratedQuestion
from tests.conftest import requires_db

client = TestClient(app)


def _signup(prefix="mock"):
    email = f"pytest_{prefix}_{uuid4().hex[:10]}@example.com"
    client.post("/auth/signup", json={"email": email, "password": "secret123", "full_name": "M"})
    token = client.post("/auth/login", json={"email": email, "password": "secret123"}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _fake_generate(topics, *, difficulty="beginner", num_questions=5, context=None):
    """Deterministic questions: correct answer is always index 0, topic carried
    through so per-section/per-topic rollups in the report are predictable."""
    t = topics[0] if topics else "general"
    return [
        GeneratedQuestion(
            stem=f"{t} Q{i}",
            options=["right", "wrong", "nope", "no"],
            correct_index=0,
            explanation="because the first option is right",
            topic=t,
            difficulty=difficulty,
        )
        for i in range(num_questions)
    ]


@pytest.fixture(autouse=True)
def _patch_generator(monkeypatch):
    monkeypatch.setattr(gen_mod, "generate", _fake_generate)


# ── auto generation from topics ──────────────────────────────────────────────────
@requires_db
def test_auto_generate_builds_one_section_per_topic():
    headers = _signup()
    client.put("/preferences/me", headers=headers, json={"topics": ["python", "sql", "linux"]})

    r = client.post(
        "/assessments/mock-tests/generate",
        headers=headers,
        json={"num_sections": 2, "questions_per_section": 3, "difficulty": "intermediate"},
    )
    assert r.status_code == 200, r.text
    test = r.json()
    assert len(test["sections"]) == 2  # capped at num_sections
    assert test["total_questions"] == 6
    assert [s["title"] for s in test["sections"]] == ["python", "sql"]
    # timed: 3 questions * 60s per section, summed into the overall limit
    assert all(s["duration_seconds"] == 180 for s in test["sections"])
    assert test["duration_seconds"] == 360
    assert test["submitted_at"] is None
    # taker view hides the answer key
    q = test["sections"][0]["questions"][0]
    assert "correct_index" not in q and "explanation" not in q


# ── explicit sections ──────────────────────────────────────────────────────────────
@requires_db
def test_explicit_sections_honoured():
    headers = _signup()
    r = client.post(
        "/assessments/mock-tests/generate",
        headers=headers,
        json={
            "title": "GATE Mock",
            "difficulty": "advanced",
            "sections": [
                {"title": "Quant", "topics": ["algebra"], "num_questions": 2, "duration_minutes": 10},
                {"title": "Verbal", "topics": ["grammar"], "num_questions": 3},
            ],
        },
    )
    assert r.status_code == 200, r.text
    test = r.json()
    assert test["title"] == "GATE Mock"
    assert [s["title"] for s in test["sections"]] == ["Quant", "Verbal"]
    assert test["sections"][0]["duration_seconds"] == 600  # 10 min override
    assert test["sections"][1]["duration_seconds"] == 180  # default 3 * 60
    assert test["total_questions"] == 5


# ── full flow: take → submit → report, single submission ────────────────────────────
@requires_db
def test_take_submit_and_report():
    headers = _signup()
    client.put("/preferences/me", headers=headers, json={"topics": ["python", "sql"]})
    test = client.post(
        "/assessments/mock-tests/generate",
        headers=headers,
        json={"num_sections": 2, "questions_per_section": 2, "difficulty": "intermediate"},
    ).json()
    tid = test["public_id"]

    # opening the test to take it starts the clock
    taker = client.get(f"/assessments/mock-tests/{tid}", headers=headers).json()
    assert taker["started_at"] is not None

    # answer the "python" section correctly (index 0), the "sql" section wrong (index 1)
    answers = []
    for sec in taker["sections"]:
        correct = sec["title"] == "python"
        for q in sec["questions"]:
            answers.append(
                {"question_id": q["public_id"], "selected_index": 0 if correct else 1, "time_ms": 5000}
            )

    rep = client.post(
        f"/assessments/mock-tests/{tid}/submit", headers=headers, json={"answers": answers}
    )
    assert rep.status_code == 200, rep.text
    report = rep.json()
    assert report["score"] == 2 and report["total"] == 4
    assert report["percentage"] == 50.0
    assert report["percentile"] is not None and 0 <= report["percentile"] <= 100

    # section scores: python 100%, sql 0%
    by_title = {s["title"]: s for s in report["sections"]}
    assert by_title["python"]["accuracy"] == 100.0
    assert by_title["sql"]["accuracy"] == 0.0
    assert by_title["python"]["avg_seconds_per_question"] == 5.0

    # weak areas + next steps surface the failed topic
    assert any(w["topic"] == "sql" and w["accuracy"] == 0.0 for w in report["weak_areas"])
    assert "sql" in report["next_steps"]
    assert "python" not in report["next_steps"]

    # answers carry the revealed key + explanation
    assert len(report["answers"]) == 4
    assert all("correct_index" in a and "explanation" in a for a in report["answers"])

    # time analysis present
    assert report["time"]["time_taken_seconds"] is not None
    assert report["time"]["duration_seconds"] == 240

    # single submission: a second submit is rejected
    again = client.post(
        f"/assessments/mock-tests/{tid}/submit", headers=headers, json={"answers": answers}
    )
    assert again.status_code == 409

    # the report endpoint returns the same result
    fetched = client.get(f"/assessments/mock-tests/{tid}/report", headers=headers).json()
    assert fetched["score"] == 2 and fetched["percentage"] == 50.0

    # history shows it submitted with a percentage
    history = client.get("/assessments/mock-tests", headers=headers).json()
    row = next(m for m in history if m["public_id"] == tid)
    assert row["status"] == "submitted" and row["percentage"] == 50.0


# ── guards ──────────────────────────────────────────────────────────────────────────
@requires_db
def test_no_topics_is_422():
    headers = _signup()  # no preferences/profile, no topics in body
    r = client.post("/assessments/mock-tests/generate", headers=headers, json={})
    assert r.status_code == 422


@requires_db
def test_unknown_and_unsubmitted_are_404():
    headers = _signup()
    assert client.post(
        f"/assessments/mock-tests/{uuid4()}/submit", headers=headers, json={"answers": []}
    ).status_code == 404
    assert client.get(f"/assessments/mock-tests/{uuid4()}/report", headers=headers).status_code == 404

    # generated but never submitted → report is 404
    client.put("/preferences/me", headers=headers, json={"topics": ["python"]})
    test = client.post(
        "/assessments/mock-tests/generate", headers=headers, json={"num_sections": 1}
    ).json()
    assert client.get(
        f"/assessments/mock-tests/{test['public_id']}/report", headers=headers
    ).status_code == 404
