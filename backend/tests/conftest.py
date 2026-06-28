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


def _reset_identity_sequences(conn: psycopg.Connection) -> None:
    """Set every public `id` identity sequence to MAX(id)+1 (or 1 if the table is
    empty), so deleting test rows doesn't leave the counter climbing."""
    tables = conn.execute(
        "select table_name from information_schema.columns "
        "where table_schema = 'public' and column_name = 'id' and is_identity = 'YES'"
    ).fetchall()
    for (table,) in tables:
        conn.execute(
            f"select setval(pg_get_serial_sequence('{table}', 'id'), "
            f"coalesce((select max(id) from {table}), 1), "
            f"(select max(id) from {table}) is not null)"
        )


@pytest.fixture(scope="session", autouse=True)
def _purge_test_data():
    """After the whole test session, remove what the tests created and reset the
    id counters. Tests sign up users with a ``pytest_`` email prefix; deleting
    those cascades to their profiles/preferences/feed_items/saved_resources, and
    we then drop any canonical resource left unreferenced (its chunks cascade).
    Keeps a shared/dev database free of test rows and runaway IDs."""
    yield
    if not _db_ready():
        return
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("delete from users where email like 'pytest\\_%'")
        conn.execute(
            "delete from resources r "
            "where not exists (select 1 from feed_items f where f.resource_id = r.id) "
            "and not exists (select 1 from saved_resources s where s.resource_id = r.id)"
        )
        conn.commit()
        _reset_identity_sequences(conn)
        conn.commit()
