"""Tiny forward-only SQL migration runner — no ORM, no Alembic.

Migrations are plain ``.sql`` files in ``app/db/migrations/`` named
``NNNN_description.sql`` and applied in filename order. Applied versions are
tracked in a ``schema_migrations`` table; each file runs once, in a transaction.

Run with:  python -m app.db.migrate
"""

from __future__ import annotations

import pathlib
import psycopg

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"

def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute("""
        create table if not exists schema_migrations (
            version    text primary key,
            applied_at timestamptz not null default now()
        )
        """)
    conn.commit()

def run() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(settings.database_url, autocommit=False) as conn:
        _ensure_tracking_table(conn)

        applied = {
            row[0] for row in conn.execute("select version from schema_migrations").fetchall()
        }

        for path in files:
            version = path.stem
            if version in applied:
                logger.info("skip   %s (already applied)", version)
                continue

            logger.info("apply  %s", version)
            sql = path.read_text()

            with conn.transaction():
                conn.execute(sql)  # psycopg3 runs multi-statement SQL in one execute
                conn.execute("insert into schema_migrations (version) values (%s)", (version,))
        logger.info("migrations up to date (%d files)", len(files))

if __name__ == "__main__":
    run()
