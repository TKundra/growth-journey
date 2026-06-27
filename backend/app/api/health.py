"""Health / readiness endpoints."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import settings
from app.db import get_conn

router = APIRouter(tags=["health"])

@router.get("/health")
def health() -> dict:
    """Liveness — process is up."""
    return {"status": "ok", "version": __version__, "env": settings.app_env}

@router.get("/health/db")
def health_db(conn: psycopg.Connection = Depends(get_conn)) -> dict:
    """Readiness — database is reachable (raw query)."""
    conn.execute("select 1")
    return {"status": "ok", "database": "reachable"}
