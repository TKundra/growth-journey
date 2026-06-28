"""Phase 3 integration test: generate → take → submit → result → stats.

LLM generation is monkeypatched (no API key / network) so this exercises the real
routes + SQL: question-bank persistence, the taker view hiding the answer key,
deterministic scoring, and per-topic progress aggregation.
Requires a database with migrations applied; skipped otherwise (see conftest).
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.assessments import generator as gen_mod
from app.modules.assessments.schemas import GeneratedQuestion
from tests.conftest import requires_db

client = TestClient(app)


def _signup_with_prefs(topics):
    email = f"pytest_qz_{uuid4().hex[:10]}@example.com"
    client.post("/auth/signup", json={"email": email, "password": "secret123"})
    token = client.post("/auth/login", json={"email": email, "password": "secret123"}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        "/preferences/me", headers=headers, json={"topics": topics, "difficulty": "beginner"}
    )
    return headers


# Two topics so per-topic stats have something to split on. Correct indices vary
# so a "always pick 0" submission can't accidentally pass.
_FAKE_QUESTIONS = [
    GeneratedQuestion(
        stem="Capital of France?",
        options=["Berlin", "Paris", "Rome", "Madrid"],
        correct_index=1,
        explanation="Paris is the capital of France.",
        topic="Geography",
    ),
    GeneratedQuestion(
        stem="2 + 2 = ?",
        options=["3", "4", "5", "6"],
        correct_index=1,
        explanation="Basic arithmetic.",
        topic="Math",
    ),
    GeneratedQuestion(
        stem="Largest planet?",
        options=["Jupiter", "Mars", "Earth", "Venus"],
        correct_index=0,
        explanation="Jupiter is the largest planet.",
        topic="Geography",
    ),
]


@pytest.fixture
def _stub_generate(monkeypatch):
    monkeypatch.setattr(
        gen_mod, "generate", lambda topics, **kw: [q.model_copy() for q in _FAKE_QUESTIONS]
    )


@requires_db
def test_generate_requires_topics():
    headers = _signup_with_prefs([])  # nothing to quiz on
    r = client.post("/assessments/quizzes/generate", headers=headers, json={})
    assert r.status_code == 422


@requires_db
def test_full_quiz_flow(_stub_generate):
    headers = _signup_with_prefs(["Geography", "Math"])

    # generate
    r = client.post(
        "/assessments/quizzes/generate", headers=headers, json={"num_questions": 3}
    )
    assert r.status_code == 200
    quiz = r.json()
    assert quiz["num_questions"] == 3
    qids = [q["public_id"] for q in quiz["questions"]]
    # taker view must NOT leak the answer key
    assert all("correct_index" not in q and "explanation" not in q for q in quiz["questions"])
    assert all(len(q["options"]) == 4 for q in quiz["questions"])

    pid = quiz["public_id"]

    # fetch the quiz back — same questions, still no answers
    got = client.get(f"/assessments/quizzes/{pid}", headers=headers).json()
    assert [q["public_id"] for q in got["questions"]] == qids

    # submit: answer Q1 + Q3 correctly, Q2 wrong → 2/3
    answers = [
        {"question_id": qids[0], "selected_index": 1},  # correct (Paris)
        {"question_id": qids[1], "selected_index": 0},  # wrong (3, not 4)
        {"question_id": qids[2], "selected_index": 0},  # correct (Jupiter)
    ]
    res = client.post(
        f"/assessments/quizzes/{pid}/submit", headers=headers, json={"answers": answers}
    ).json()
    assert res["score"] == 2 and res["total"] == 3
    assert res["percentage"] == pytest.approx(66.7)
    by_q = {a["question_id"]: a for a in res["answers"]}
    assert by_q[qids[0]]["is_correct"] is True
    assert by_q[qids[1]]["is_correct"] is False
    assert by_q[qids[1]]["correct_index"] == 1  # answer key revealed on submit
    assert by_q[qids[0]]["explanation"]  # explanation revealed on submit

    # result returns the latest attempt
    result = client.get(f"/assessments/quizzes/{pid}/result", headers=headers).json()
    assert result["score"] == 2 and result["total"] == 3
    assert len(result["answers"]) == 3

    # history lists the quiz with attempt count + best score
    history = client.get("/assessments/quizzes", headers=headers).json()
    row = next(h for h in history if h["public_id"] == pid)
    assert row["attempt_count"] == 1 and row["best_score"] == 2

    # stats: overall 2/3; Geography 2/2 (100%), Math 0/1 (0%)
    stats = client.get("/assessments/stats", headers=headers).json()
    assert stats["answered"] == 3 and stats["correct"] == 2
    per = {t["topic"]: t for t in stats["per_topic"]}
    assert per["Geography"]["correct"] == 2 and per["Geography"]["accuracy"] == 100.0
    assert per["Math"]["correct"] == 0 and per["Math"]["accuracy"] == 0.0


@requires_db
def test_get_unknown_quiz_404(_stub_generate):
    headers = _signup_with_prefs(["Math"])
    assert client.get(f"/assessments/quizzes/{uuid4()}", headers=headers).status_code == 404
    assert (
        client.get(f"/assessments/quizzes/{uuid4()}/result", headers=headers).status_code == 404
    )
    assert (
        client.post(
            f"/assessments/quizzes/{uuid4()}/submit", headers=headers, json={"answers": []}
        ).status_code
        == 404
    )


@requires_db
def test_blank_answers_score_zero(_stub_generate):
    """A question left blank (no selected_index) is wrong, never a crash."""
    headers = _signup_with_prefs(["Geography", "Math"])
    quiz = client.post(
        "/assessments/quizzes/generate", headers=headers, json={"num_questions": 3}
    ).json()
    # submit with no answers at all
    res = client.post(
        f"/assessments/quizzes/{quiz['public_id']}/submit", headers=headers, json={"answers": []}
    ).json()
    assert res["score"] == 0 and res["total"] == 3
    assert all(a["selected_index"] is None and not a["is_correct"] for a in res["answers"])
