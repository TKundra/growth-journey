"""Phase 0 smoke tests: the app boots and liveness responds.

The /health/db test is skipped unless a database is reachable, so `pytest`
passes on a bare checkout without docker compose running.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root_ok():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "student-journey"
