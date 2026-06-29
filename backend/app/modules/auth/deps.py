"""Auth dependency: resolve the current user from a Bearer JWT.

Other modules import ``get_current_user`` to protect their routes. The returned
dict includes the internal ``id`` (for FK use) — routers should serialize via a
response_model so it never leaks.
"""

from __future__ import annotations

import psycopg
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.db import get_conn
from app.modules.auth import repository as users_repo

_bearer = HTTPBearer(auto_error=True)

def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    public_id = decode_access_token(creds.credentials)
    if public_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = users_repo.get_by_public_id(conn, public_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Gate admin-only routes (course authoring, the future import path).

    Layered on get_current_user, so it still 401s an anonymous caller; a valid
    non-admin user gets a 403."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
