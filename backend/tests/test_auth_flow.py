"""Phase 1 integration test: signup → login → verify → profile → preferences.

Requires a database with migrations applied; skipped otherwise (see conftest).
Each run uses a unique email so it's repeatable without cleanup.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import requires_db

client = TestClient(app)


def _unique_email() -> str:
    return f"pytest_{uuid4().hex[:10]}@example.com"


def _auth_header(email: str, password: str = "secret123") -> dict:
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


@requires_db
def test_signup_login_and_duplicate():
    email = _unique_email()

    r = client.post("/auth/signup", json={"email": email, "password": "secret123"})
    assert r.status_code == 201
    body = r.json()
    assert body["user_type"] is None and body["is_email_verified"] is False

    # duplicate email is rejected
    assert (
        client.post("/auth/signup", json={"email": email, "password": "secret123"}).status_code
        == 409
    )

    # login works; wrong password does not
    assert (
        client.post("/auth/login", json={"email": email, "password": "secret123"}).status_code
        == 200
    )
    assert client.post("/auth/login", json={"email": email, "password": "nope"}).status_code == 401


@requires_db
def test_email_verification():
    email = _unique_email()
    token = client.post("/auth/signup", json={"email": email, "password": "secret123"}).json()[
        "email_verification_token"
    ]
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["is_email_verified"] is True
    # token can't be reused
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


@requires_db
def test_requires_auth():
    assert client.get("/auth/me").status_code == 401  # no credentials
    assert (
        client.get("/users/me/profile", headers={"Authorization": "Bearer bad"}).status_code == 401
    )


@requires_db
def test_profile_type_switch_replaces_branch():
    email = _unique_email()
    client.post("/auth/signup", json={"email": email, "password": "secret123"})
    headers = _auth_header(email)

    # student first
    r = client.put(
        "/users/me/profile",
        headers=headers,
        json={
            "user_type": "student",
            "education_level": "undergraduate",
            "subjects": ["physics", "math"],
            "target_exams": ["JEE"],
        },
    )
    assert r.status_code == 200
    assert r.json()["profile"]["subjects"] == ["physics", "math"]

    # switch to professional — student fields must be gone
    r = client.put(
        "/users/me/profile",
        headers=headers,
        json={
            "user_type": "professional",
            "experience_years": 5,
            "role": "Backend Engineer",
            "skills": ["python", "sql"],
        },
    )
    assert r.status_code == 200
    agg = r.json()
    assert agg["user"]["user_type"] == "professional"
    assert agg["profile"]["role"] == "Backend Engineer"
    assert "subjects" not in agg["profile"]


@requires_db
def test_preferences_upsert_and_dashboard():
    email = _unique_email()
    client.post("/auth/signup", json={"email": email, "password": "secret123"})
    headers = _auth_header(email)

    # no preferences yet
    assert client.get("/preferences/me", headers=headers).status_code == 404

    r = client.put(
        "/preferences/me",
        headers=headers,
        json={"topics": ["sql"], "cadence": "weekly", "difficulty": "intermediate"},
    )
    assert r.status_code == 200 and r.json()["cadence"] == "weekly"

    # dashboard aggregate reflects it
    agg = client.get("/users/me/profile", headers=headers).json()
    assert agg["preferences"]["topics"] == ["sql"]
    assert agg["preferences"]["difficulty"] == "intermediate"
