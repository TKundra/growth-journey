"""Shared test fixtures / markers.

``requires_db`` skips a test unless the database is reachable AND Phase 1
migrations have been applied — so `pytest` stays green on a bare checkout
(no docker compose), same policy as the Phase 0 health test.
"""

from __future__ import annotations

import psycopg
import pytest

from app.core.config import settings


def _db_ready() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            return conn.execute("select to_regclass('public.users')").fetchone()[0] is not None
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _db_ready(),
    reason="database not reachable or migrations not applied (run: python -m app.db.migrate)",
)
