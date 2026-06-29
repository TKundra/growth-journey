"""Phase 4 integration tests: admin authoring + learner enrolment/progress/
certificate, the role gate, public certificate verification, and the course→
study/quiz topic seam.

Exercises the real routes + SQL. Role elevation is done directly in the DB
(there's no API to grant admin). Requires a migrated database; skipped otherwise.
"""

from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.assessments import generator as gen_mod
from app.modules.assessments.schemas import GeneratedQuestion
from tests.conftest import requires_db

client = TestClient(app)


def _signup(prefix="lc"):
    email = f"pytest_{prefix}_{uuid4().hex[:10]}@example.com"
    client.post("/auth/signup", json={"email": email, "password": "secret123", "full_name": "T"})
    token = client.post("/auth/login", json={"email": email, "password": "secret123"}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _make_admin():
    email, headers = _signup("admin")
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("update users set role = 'admin' where email = %s", (email,))
        conn.commit()
    # re-login so a fresh token's user row reflects admin (role is read per-request anyway)
    return headers


def _course_payload(**over):
    slug = over.pop("slug", f"pytest-course-{uuid4().hex[:8]}")
    body = {
        "slug": slug,
        "title": "Intro to Kubernetes",
        "subtitle": "Containers at scale",
        "description": "A short course.",
        "level": "beginner",
        "category": "Engineering",
        "tags": ["kubernetes", "containers"],
        "emoji": "☸️",
        "is_published": True,
        "modules": [
            {
                "title": "Basics",
                "summary": "",
                "lessons": [
                    {"title": "Pods", "content": "x", "topics": ["kubernetes", "pods"], "est_minutes": 20},
                    {"title": "Services", "content": "y", "topics": ["services"], "est_minutes": 25},
                ],
            },
            {
                "title": "Scaling",
                "lessons": [
                    {"title": "Deployments", "content": "z", "topics": ["deployments"]},
                ],
            },
        ],
    }
    body.update(over)
    return body


# ── role gate ──────────────────────────────────────────────────────────────────
@requires_db
def test_admin_routes_require_admin():
    _, learner = _signup()
    assert client.get("/admin/courses", headers=learner).status_code == 403
    assert client.post("/admin/courses", headers=learner, json=_course_payload()).status_code == 403
    # anonymous → 401 (no bearer)
    assert client.get("/admin/courses").status_code in (401, 403)


# ── admin authoring (== ETL contract) ────────────────────────────────────────────
@requires_db
def test_admin_create_and_idempotent_upsert():
    admin = _make_admin()
    payload = _course_payload()
    r = client.post("/admin/courses", headers=admin, json=payload)
    assert r.status_code == 201, r.text
    detail = r.json()
    assert detail["module_count"] == 2 and detail["lesson_count"] == 3
    assert [m["position"] for m in detail["modules"]] == [0, 1]
    assert detail["modules"][0]["lessons"][0]["position"] == 0

    # re-POST same slug → replace, not duplicate
    again = client.post("/admin/courses", headers=admin, json=payload)
    assert again.status_code == 201
    all_courses = client.get("/admin/courses", headers=admin).json()
    assert sum(1 for c in all_courses if c["slug"] == payload["slug"]) == 1


# ── full learner flow → certificate ──────────────────────────────────────────────
@requires_db
def test_enroll_progress_and_certificate():
    admin = _make_admin()
    payload = _course_payload()
    course = client.post("/admin/courses", headers=admin, json=payload).json()
    cid = course["public_id"]

    _, learner = _signup()

    # published course is visible in the catalog
    catalog = client.get("/courses", headers=learner).json()
    assert any(c["public_id"] == cid for c in catalog)

    # detail shows the tree, not enrolled yet
    detail = client.get(f"/courses/{cid}", headers=learner).json()
    assert detail["is_enrolled"] is False
    lesson_ids = [l["public_id"] for m in detail["modules"] for l in m["lessons"]]
    assert len(lesson_ids) == 3

    # marking a lesson before enrolling is rejected
    assert client.post(f"/courses/lessons/{lesson_ids[0]}/complete", headers=learner).status_code == 404

    # enroll
    enr = client.post(f"/courses/{cid}/enroll", headers=learner).json()
    assert enr["status"] == "active" and enr["progress"] == 0 and enr["certificate"] is None

    # complete 1 of 3 → 33%, still active, no certificate
    after1 = client.post(f"/courses/lessons/{lesson_ids[0]}/complete", headers=learner).json()
    assert after1["progress"] == 33 and after1["status"] == "active"
    assert after1["certificate"] is None

    # idempotent: re-completing the same lesson doesn't double-count
    again = client.post(f"/courses/lessons/{lesson_ids[0]}/complete", headers=learner).json()
    assert again["progress"] == 33

    # finish the rest → 100%, completed, certificate issued
    for lid in lesson_ids[1:]:
        last = client.post(f"/courses/lessons/{lid}/complete", headers=learner).json()
    assert last["progress"] == 100 and last["status"] == "completed"
    cert = last["certificate"]
    assert cert and cert["serial"].startswith("JNY-")

    # appears under my-courses + my-certificates
    mine = client.get("/courses/me", headers=learner).json()
    assert any(e["course"]["public_id"] == cid and e["status"] == "completed" for e in mine)
    my_certs = client.get("/certificates/me", headers=learner).json()
    assert any(c["serial"] == cert["serial"] for c in my_certs)

    # public verify page (no auth) renders the serial; revoke flips the banner
    v = client.get(f"/certificates/verify/{cert['public_id']}")
    # ".revoked" appears in the CSS regardless; the banner text only when revoked.
    assert v.status_code == 200 and cert["serial"] in v.text and "has been revoked" not in v.text.lower()
    assert client.post(
        f"/admin/certificates/{cert['public_id']}/revoke", headers=admin
    ).json()["revoked"] is True
    v2 = client.get(f"/certificates/verify/{cert['public_id']}")
    assert "has been revoked" in v2.text.lower()

    # unknown certificate id → 404 page
    assert client.get(f"/certificates/verify/{uuid4()}").status_code == 404


# ── recommendations exclude enrolled + rank by overlap ────────────────────────────
@requires_db
def test_recommendations_exclude_enrolled():
    admin = _make_admin()
    course = client.post("/admin/courses", headers=admin, json=_course_payload()).json()
    cid = course["public_id"]

    _, learner = _signup()
    client.put("/preferences/me", headers=learner, json={"topics": ["kubernetes"]})
    rec_before = client.get("/courses/recommended", headers=learner).json()
    assert any(c["public_id"] == cid for c in rec_before)  # topic overlap surfaces it

    client.post(f"/courses/{cid}/enroll", headers=learner)
    rec_after = client.get("/courses/recommended", headers=learner).json()
    assert all(c["public_id"] != cid for c in rec_after)  # enrolled → dropped


# ── the course→quiz topic seam ────────────────────────────────────────────────────
@requires_db
def test_course_id_grounds_quiz_topics(monkeypatch):
    captured = {}

    def _fake_generate(topics, **kw):
        captured["topics"] = topics
        return [
            GeneratedQuestion(
                stem="Q?", options=["a", "b"], correct_index=0, topic=topics[0] if topics else ""
            )
        ]

    monkeypatch.setattr(gen_mod, "generate", _fake_generate)

    admin = _make_admin()
    course = client.post("/admin/courses", headers=admin, json=_course_payload()).json()
    cid = course["public_id"]

    _, learner = _signup()  # no preferences/profile topics at all
    # topics endpoint aggregates the syllabus
    topics_out = client.get(f"/courses/{cid}/topics", headers=learner).json()
    assert "kubernetes" in topics_out["topics"]

    # generating a quiz with course_id grounds it in those syllabus topics
    r = client.post(
        "/assessments/quizzes/generate", headers=learner, json={"course_id": cid, "num_questions": 1}
    )
    assert r.status_code == 200, r.text
    assert any(t in captured["topics"] for t in ("kubernetes", "pods", "services", "deployments"))
