"""Raw-SQL data access for study material (feed, library, RAG chunks).

Resources are normalized: `resources` is canonical and URL-unique (shared across
all users), `feed_items` is the per-user feed (topic + rank for that user). The
API still exposes one flat resource shape — `_USER_RESOURCE_COLS` joins the two
and reuses the canonical `public_id` as the resource's external id.
"""

from __future__ import annotations

import psycopg

from app.modules.study_material.curator import domain_of
from app.modules.study_material.schemas import CuratedItem

# A resource as seen by one user: canonical fields from `resources` (res) +
# per-user fields from `feed_items` (f). `is_saved` is computed via EXISTS using
# f.user_id, so callers only need `f` joined for the current user (no extra param).
_USER_RESOURCE_COLS = """
    res.public_id, res.title, res.url, res.source_domain, res.summary,
    f.topic, res.tags, res.difficulty, res.kind, res.est_minutes,
    f.relevance, f.created_at,
    exists (
        select 1 from saved_resources s
        where s.resource_id = res.id and s.user_id = f.user_id
    ) as is_saved
"""

def upsert_resources(
    conn: psycopg.Connection, user_id: int, items: list[CuratedItem]
) -> list[dict]:
    """Upsert curated items: canonical resource (deduped by URL, shared across
    users) + this user's feed entry. Re-running refreshes both in place."""
    out: list[dict] = []
    for it in items:
        rid = conn.execute(
            """
            insert into resources
                (url, title, source_domain, summary, tags, difficulty, kind, est_minutes)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (url) do update set
                title         = excluded.title,
                source_domain = excluded.source_domain,
                summary       = excluded.summary,
                tags          = excluded.tags,
                difficulty    = excluded.difficulty,
                kind          = excluded.kind,
                est_minutes   = excluded.est_minutes
            returning id
            """,
            (
                it.url,
                it.title,
                domain_of(it.url),
                it.summary,
                it.tags,
                it.difficulty,
                it.kind,
                it.est_minutes,
            ),
        ).fetchone()["id"]
        conn.execute(
            """
            insert into feed_items (user_id, resource_id, topic, relevance)
            values (%s, %s, %s, %s)
            on conflict (user_id, resource_id) do update set
                topic     = excluded.topic,
                relevance = excluded.relevance
            """,
            (user_id, rid, it.topic, it.relevance),
        )
        row = conn.execute(
            f"""
            select {_USER_RESOURCE_COLS}
            from feed_items f
            join resources res on res.id = f.resource_id
            where f.user_id = %s and res.id = %s
            """,
            (user_id, rid),
        ).fetchone()
        out.append(row)
    conn.commit()
    return out

def list_resources(
    conn: psycopg.Connection, user_id: int, *, saved_only: bool = False, limit: int = 50
) -> list[dict]:
    where = "f.user_id = %s"
    if saved_only:
        where += (
            " and exists (select 1 from saved_resources s "
            "where s.resource_id = res.id and s.user_id = f.user_id)"
        )
    return conn.execute(
        f"""
        select {_USER_RESOURCE_COLS}
        from feed_items f
        join resources res on res.id = f.resource_id
        where {where}
        order by f.relevance desc nulls last, f.created_at desc
        limit %s
        """,
        (user_id, limit),
    ).fetchall()

def get_resource(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    return conn.execute(
        f"""
        select {_USER_RESOURCE_COLS}
        from feed_items f
        join resources res on res.id = f.resource_id
        where f.user_id = %s and res.public_id = %s
        """,
        (user_id, public_id),
    ).fetchone()

def _feed_resource_id(conn: psycopg.Connection, user_id: int, public_id: str) -> int | None:
    """Canonical resource id for a public_id, but only if it's in this user's feed
    (authorizes save/unsave: a user can only act on resources surfaced to them)."""
    row = conn.execute(
        """
        select res.id
        from resources res
        join feed_items f on f.resource_id = res.id and f.user_id = %s
        where res.public_id = %s
        """,
        (user_id, public_id),
    ).fetchone()
    return row["id"] if row else None

def save_resource(
    conn: psycopg.Connection, user_id: int, resource_public_id: str, note: str | None
) -> dict | None:
    """Promote a feed item into the library. Returns the saved row + its resource."""
    rid = _feed_resource_id(conn, user_id, resource_public_id)
    if rid is None:
        return None
    saved = conn.execute(
        """
        insert into saved_resources (user_id, resource_id, note)
        values (%s, %s, %s)
        on conflict (user_id, resource_id) do update set note = excluded.note
        returning public_id, note, created_at
        """,
        (user_id, rid, note),
    ).fetchone()
    conn.commit()
    resource = get_resource(conn, user_id, resource_public_id)
    return {**saved, "resource": resource}

def unsave_resource(conn: psycopg.Connection, user_id: int, resource_public_id: str) -> bool:
    rid = _feed_resource_id(conn, user_id, resource_public_id)
    if rid is None:
        return False
    cur = conn.execute(
        "delete from saved_resources where user_id = %s and resource_id = %s",
        (user_id, rid),
    )
    conn.commit()
    return cur.rowcount > 0

def list_saved(conn: psycopg.Connection, user_id: int, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        f"""
        select s.public_id as saved_public_id, s.note, s.created_at as saved_created_at,
               {_USER_RESOURCE_COLS}
        from saved_resources s
        join resources res on res.id = s.resource_id
        join feed_items f on f.resource_id = res.id and f.user_id = s.user_id
        where s.user_id = %s
        order by s.created_at desc
        limit %s
        """,
        (user_id, limit),
    ).fetchall()
    # Split the flat row into the saved-row shell + nested resource (alias the
    # saved-row columns so they don't collide with the resource's public_id/created_at).
    out: list[dict] = []
    for row in rows:
        saved = {
            "public_id": row.pop("saved_public_id"),
            "note": row.pop("note"),
            "created_at": row.pop("saved_created_at"),
        }
        out.append({**saved, "resource": row})
    return out

# ── RAG (resource_chunks) ─────────────────────────────────────────────────────
def _resource_id(conn: psycopg.Connection, public_id: str) -> int | None:
    """Canonical resource id by public_id (no user scoping — chunks are shared)."""
    row = conn.execute("select id from resources where public_id = %s", (public_id,)).fetchone()
    return row["id"] if row else None

def chunks_exist(conn: psycopg.Connection, resource_public_id: str) -> bool:
    """True if this (canonical) resource is already embedded — lets indexing reuse
    another user's vectors instead of re-embedding the same URL."""
    return (
        conn.execute(
            """
        select 1 from resource_chunks c
        join resources r on r.id = c.resource_id
        where r.public_id = %s and c.embedding is not null
        limit 1
        """,
            (resource_public_id,),
        ).fetchone()
        is not None
    )

def replace_chunks(
    conn: psycopg.Connection,
    resource_public_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    rid = _resource_id(conn, resource_public_id)
    if rid is None:
        return 0
    conn.execute("delete from resource_chunks where resource_id = %s", (rid,))
    for i, (content, emb) in enumerate(zip(chunks, embeddings)):
        conn.execute(
            "insert into resource_chunks (resource_id, chunk_index, content, embedding) "
            "values (%s, %s, %s, %s)",
            (rid, i, content, _vector_literal(emb)),
        )
    conn.commit()
    return len(chunks)

def search_saved_chunks(
    conn: psycopg.Connection, user_id: int, embedding: list[float], *, k: int = 5
) -> list[dict]:
    """Cosine-similarity search over the user's saved (indexed) material."""
    return conn.execute(
        f"""
        select {_USER_RESOURCE_COLS},
               1 - (c.embedding <=> %s) as score
        from resource_chunks c
        join resources res on res.id = c.resource_id
        join saved_resources s on s.resource_id = res.id and s.user_id = %s
        join feed_items f on f.resource_id = res.id and f.user_id = s.user_id
        where c.embedding is not null
        order by c.embedding <=> %s
        limit %s
        """,
        (_vector_literal(embedding), user_id, _vector_literal(embedding), k),
    ).fetchall()

def _vector_literal(vec: list[float]) -> str:
    """pgvector accepts a text literal like '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
