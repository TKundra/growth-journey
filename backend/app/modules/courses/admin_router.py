"""Admin course-authoring routes (role='admin' only).

This is the canonical write path for the catalog — and, by design, the contract
a future ETL import job targets: POST a CourseUpsertIn (nested modules+lessons)
and it is created or replaced idempotently (by slug, or by (source, external_ref)
for imports). Org data is onboarded later by transforming it into this payload.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db import get_conn
from app.modules.auth.deps import require_admin
from app.modules.courses import repository as repo
from app.modules.courses.schemas import CourseDetail, CourseUpsertIn

# Every route here is admin-gated at the router level.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# ── course authoring ─────────────────────────────────────────────────────────
@router.get("/courses")
def list_all_courses(
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.admin_list_courses(conn)

@router.post("/courses", response_model=CourseDetail, status_code=status.HTTP_201_CREATED)
def upsert_course(
    body: CourseUpsertIn,
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Create or idempotently replace a course + its full module/lesson tree."""
    return repo.upsert_course(conn, admin["id"], body)

@router.get("/courses/{public_id}", response_model=CourseDetail)
def get_course(
    public_id: str,
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    course = repo.admin_get_course(conn, public_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course

@router.post("/courses/{public_id}/publish", response_model=CourseDetail)
def set_publish(
    public_id: str,
    published: bool = Query(True),
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    if not repo.set_published(conn, public_id, published):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return repo.admin_get_course(conn, public_id)

@router.delete("/courses/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    public_id: str,
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> None:
    if not repo.delete_course(conn, public_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

# ── enrollment oversight ─────────────────────────────────────────────────────
@router.get("/enrollments")
def list_enrollments(
    course: str | None = Query(None, description="Filter by course public_id"),
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.admin_list_enrollments(conn, course_public_id=course)

# ── certificate revocation ───────────────────────────────────────────────────
@router.post("/certificates/{public_id}/revoke")
def revoke_certificate(
    public_id: str,
    revoked: bool = Query(True),
    admin: dict = Depends(require_admin),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    if not repo.set_certificate_revoked(conn, public_id, revoked):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return {"public_id": public_id, "revoked": revoked}
