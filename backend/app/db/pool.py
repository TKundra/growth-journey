"""psycopg3 connection pool + FastAPI dependency.

Connections use ``dict_row`` so raw queries return dicts (``row["email"]``),
which keeps hand-written SQL readable. The pool is built lazily on first use so
the app still boots (and health/liveness still works) without a database.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

@lru_cache
def get_pool() -> ConnectionPool:
    pool = ConnectionPool(
        conninfo=settings.database_url,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=10,
        open=False,
    )
    pool.open()
    return pool

def get_conn() -> Generator[psycopg.Connection, None, None]:
    """FastAPI dependency: yield a pooled connection.

    The connection is returned to the pool on exit. Each request gets its own
    connection; call ``conn.commit()`` after writes (autocommit is off).
    """
    with get_pool().connection() as conn:
        yield conn
