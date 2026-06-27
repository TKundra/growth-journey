"""Raw-SQL data access for preferences (one row per user, upserted)."""

from __future__ import annotations

import psycopg

from app.modules.preferences.schemas import PreferencesIn

_COLS = "public_id, topics, goal, cadence, difficulty, notifications_enabled, updated_at"

def upsert(conn: psycopg.Connection, user_id: int, data: PreferencesIn) -> dict:
    row = conn.execute(
        f"""
        insert into preferences
            (user_id, topics, goal, cadence, difficulty, notifications_enabled)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (user_id) do update set
            topics                = excluded.topics,
            goal                  = excluded.goal,
            cadence               = excluded.cadence,
            difficulty            = excluded.difficulty,
            notifications_enabled = excluded.notifications_enabled
        returning {_COLS}
        """,
        (
            user_id,
            data.topics,
            data.goal,
            data.cadence,
            data.difficulty,
            data.notifications_enabled,
        ),
    ).fetchone()
    conn.commit()
    return row

def get(conn: psycopg.Connection, user_id: int) -> dict | None:
    return conn.execute(
        f"select {_COLS} from preferences where user_id = %s",
        (user_id,),
    ).fetchone()
