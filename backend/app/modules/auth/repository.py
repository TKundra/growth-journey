"""Raw-SQL data access for users. No ORM — psycopg3 with dict rows.

Repositories take an open connection (from the ``get_conn`` dependency) and
commit their own writes. Rows come back as dicts; callers map them to schemas.
"""

from __future__ import annotations

import psycopg

# Columns safe to return to callers (never the password_hash).
_PUBLIC_COLS = "public_id, email, full_name, user_type, is_email_verified, created_at"

def create_user(
    conn: psycopg.Connection, *, email: str, password_hash: str, full_name: str | None
) -> dict:
    """Insert a user and return its public columns + the verification token."""
    row = conn.execute(
        f"""
        insert into users (email, password_hash, full_name, email_verification_token)
        values (%s, %s, %s, uuidv7())
        returning {_PUBLIC_COLS}, email_verification_token
        """,
        (email, password_hash, full_name),
    ).fetchone()
    conn.commit()
    return row

def get_by_email_with_hash(conn: psycopg.Connection, email: str) -> dict | None:
    """For login: includes password_hash. Do not return this to clients."""
    return conn.execute(
        f"select id, password_hash, {_PUBLIC_COLS} from users where email = %s",
        (email,),
    ).fetchone()

def get_by_public_id(conn: psycopg.Connection, public_id: str) -> dict | None:
    """For the auth dependency: includes internal ``id`` for FK use, never the hash."""
    return conn.execute(
        f"select id, {_PUBLIC_COLS} from users where public_id = %s",
        (public_id,),
    ).fetchone()

def verify_email(conn: psycopg.Connection, token: str) -> dict | None:
    """Mark verified by token. Returns the user, or None if token is unknown/used."""
    row = conn.execute(
        f"""
        update users
        set is_email_verified = true, email_verification_token = null
        where email_verification_token = %s and is_email_verified = false
        returning {_PUBLIC_COLS}
        """,
        (token,),
    ).fetchone()
    conn.commit()
    return row
