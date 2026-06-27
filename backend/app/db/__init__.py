"""Raw-SQL data access (psycopg3). No ORM.

Query from a pooled connection:

    from app.db import get_conn

    def list_users(conn):
        rows = conn.execute("select id, public_id, email from users").fetchall()
        return rows  # rows are dicts (dict_row factory)
"""

from app.db.pool import get_conn, get_pool

__all__ = ["get_conn", "get_pool"]
