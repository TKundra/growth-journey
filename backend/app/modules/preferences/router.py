"""Preferences routes (set / fetch the current user's learning preferences)."""

from __future__ import annotations

import psycopg

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import get_conn
from app.modules.auth.deps import get_current_user
from app.modules.preferences import repository as prefs_repo
from app.modules.preferences.schemas import PreferencesIn, PreferencesOut

router = APIRouter(prefix="/preferences", tags=["preferences"])

@router.put("/me", response_model=PreferencesOut)
def set_preferences(
    body: PreferencesIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    return prefs_repo.upsert(conn, current_user["id"], body)

@router.get("/me", response_model=PreferencesOut)
def get_preferences(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    prefs = prefs_repo.get(conn, current_user["id"])
    if prefs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No preferences set yet",
        )
    return prefs
