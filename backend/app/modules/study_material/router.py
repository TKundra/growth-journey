"""Study-material routes: generate a curated feed, browse it, and build a library.

Flow: GET preferences + profile → build queries → search → LLM curate → persist →
return the feed. Saving a resource promotes it to the library and (best-effort)
indexes it for semantic search.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.ai_core.llm import LLMNotConfigured
from app.db import get_conn
from app.modules.auth.deps import get_current_user
from app.modules.preferences import repository as prefs_repo
from app.modules.study_material import curator, query_builder, rag
from app.modules.study_material import repository as repo
from app.modules.study_material.schemas import (
    GenerateIn,
    GenerateOut,
    SaveIn,
    SavedResourceOut,
    SemanticHit,
    StudyResourceOut,
)
from app.modules.users import repository as users_repo

import psycopg

router = APIRouter(prefix="/study-material", tags=["study_material"])

_NO_LLM = "AI is not configured (set OLLAMA_API_KEY) — study material is unavailable."

@router.post("/generate", response_model=GenerateOut)
def generate(
    body: GenerateIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    prefs = prefs_repo.get(conn, current_user["id"]) or {}
    profile = users_repo.get_profile(conn, current_user)

    difficulty = body.difficulty or prefs.get("difficulty")
    topics = query_builder.resolve_topics(
        preference_topics=prefs.get("topics"),
        profile=profile,
        user_type=current_user.get("user_type"),
        overrides=body.topics,
        max_topics=body.max_topics,
    )
    if not topics:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No topics to study. Set preferences/profile or pass `topics`.",
        )

    article_queries = query_builder.build_queries(topics, difficulty=difficulty)
    video_queries = query_builder.build_video_queries(topics)
    candidates = curator.gather_candidates(article_queries, video_queries, per_topic=body.per_topic)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Web search returned no results. Check the search provider/network.",
        )

    try:
        items = curator.curate(candidates, difficulty=difficulty)
    except LLMNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_LLM)

    resources = repo.upsert_resources(conn, current_user["id"], items)
    return {"generated": len(resources), "resources": resources}

@router.get("", response_model=list[StudyResourceOut])
def list_feed(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_resources(conn, current_user["id"])

@router.get("/library", response_model=list[SavedResourceOut])
def library(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_saved(conn, current_user["id"])

@router.get("/library/search", response_model=list[SemanticHit])
def library_search(
    q: str = Query(..., min_length=2),
    k: int = Query(5, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    try:
        hits = rag.semantic_search(conn, current_user["id"], q, k=k)
    except LLMNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_LLM)
    return [{"score": h.pop("score"), "resource": h} for h in hits]

@router.get("/{public_id}", response_model=StudyResourceOut)
def get_one(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    resource = repo.get_resource(conn, current_user["id"], public_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return resource

@router.post("/{public_id}/save", response_model=SavedResourceOut)
def save(
    public_id: str,
    body: SaveIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    saved = repo.save_resource(conn, current_user["id"], public_id, body.note)
    if saved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    # Best-effort RAG indexing; never fails the save.
    rag.index_saved_resource(conn, saved["resource"])
    return saved

@router.delete("/{public_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> None:
    if not repo.unsave_resource(conn, current_user["id"], public_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not in library")
