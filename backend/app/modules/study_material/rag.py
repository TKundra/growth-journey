"""RAG indexing/retrieval for saved material.

v1 indexes the curated title + summary (the text we hold) rather than fetching
full pages — enough to power semantic search over the library and to seed Phase 3
question generation. Swapping in full-page fetch later means only changing what
text ``index_saved_resource`` chunks; the chunk/embed/store path stays the same.

All embedding work degrades gracefully: with no OLLAMA_API_KEY, indexing is a
no-op and semantic search raises LLMNotConfigured (the router maps it to 503).
"""

from __future__ import annotations

import psycopg

from app.ai_core.llm import LLMNotConfigured, get_llm
from app.core.logging import get_logger
from app.modules.study_material import repository as repo

logger = get_logger(__name__)

def chunk_text(text: str, *, size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping character windows (word-boundary aware)."""
    text = " ".join((text or "").split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Don't cut mid-word: back off to the last space in the window.
        if end < len(text):
            space = text.rfind(" ", start, end)
            if space > start:
                end = space
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]

def index_saved_resource(conn: psycopg.Connection, resource: dict) -> int:
    """Chunk + embed a saved resource. Returns chunk count (0 if not configured).

    Resources (and their chunks) are canonical/shared, so if another user already
    indexed this URL we reuse those vectors instead of re-embedding."""
    public_id = str(resource["public_id"])
    if repo.chunks_exist(conn, public_id):
        return 0
    body = " — ".join(p for p in [resource.get("title"), resource.get("summary")] if p)
    chunks = chunk_text(body)
    if not chunks:
        return 0
    try:
        embeddings = get_llm().embed(chunks)
    except LLMNotConfigured:
        logger.info(
            "rag: embeddings not configured; skipping index for %s", resource.get("public_id")
        )
        return 0
    except Exception as exc:  # noqa: BLE001 — never let indexing break a save
        logger.warning("rag: embedding failed (%s); skipping index", exc)
        return 0
    return repo.replace_chunks(conn, public_id, chunks, embeddings)

def semantic_search(
    conn: psycopg.Connection, user_id: int, query: str, *, k: int = 5
) -> list[dict]:
    """Embed the query and return the most similar saved resources with scores."""
    embedding = get_llm().embed([query])[0]  # raises LLMNotConfigured if no key
    return repo.search_saved_chunks(conn, user_id, embedding, k=k)
