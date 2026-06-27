"""User profile routes: set the type branch + profile, and the dashboard aggregate."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

import psycopg

from app.db import get_conn
from app.modules.auth.deps import get_current_user
from app.modules.preferences import repository as prefs_repo
from app.modules.users import repository as profiles_repo
from app.modules.users.schemas import (
    ProfessionalProfileIn,
    ProfileAggregateOut,
    ProfileIn,
)

router = APIRouter(prefix="/users", tags=["users"])

@router.put("/me/profile", response_model=ProfileAggregateOut)
def set_profile(
    body: ProfileIn = Body(...),
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Set the user type (professional vs student) and upsert that profile.

    The body is discriminated on ``user_type``; switching type replaces the
    previous branch's profile. Returns the full aggregate (user + profile + prefs).
    """
    if isinstance(body, ProfessionalProfileIn):
        profiles_repo.upsert_professional(conn, current_user["id"], body)
    else:
        profiles_repo.upsert_student(conn, current_user["id"], body)

    # Re-read so user_type reflects the change just made.
    fresh = {**current_user, "user_type": body.user_type}
    return {
        "user": fresh,
        "profile": profiles_repo.get_profile(conn, fresh),
        "preferences": prefs_repo.get(conn, current_user["id"]),
    }

@router.get("/me/profile", response_model=ProfileAggregateOut)
def get_profile(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Dashboard shell data: user + profile (if set) + preferences (if set)."""
    return {
        "user": current_user,
        "profile": profiles_repo.get_profile(conn, current_user),
        "preferences": prefs_repo.get(conn, current_user["id"]),
    }
