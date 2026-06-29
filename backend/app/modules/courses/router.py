"""Course routes (learner-facing) + public certificate verification.

Catalog browse + recommendations, enrollment, per-lesson mark-complete (which
recomputes progress and auto-issues a certificate at 100%), and topic
aggregation used to ground study-material / quiz generation in a course.

The certificate verify page is intentionally unauthenticated HTML so a learner
can share the link; it renders a standalone certificate (print to PDF).
"""

from __future__ import annotations

from html import escape

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from app.db import get_conn
from app.modules.auth.deps import get_current_user
from app.modules.courses import repository as repo
from app.modules.courses.schemas import (
    CertificateOut,
    CourseDetail,
    CourseSummary,
    CourseTopicsOut,
    EnrollmentOut,
)
from app.modules.preferences import repository as prefs_repo
from app.modules.study_material import query_builder
from app.modules.users import repository as users_repo

router = APIRouter(prefix="/courses", tags=["courses"])
certificates_router = APIRouter(prefix="/certificates", tags=["courses"])

# ── catalog ──────────────────────────────────────────────────────────────────
@router.get("", response_model=list[CourseSummary])
def list_catalog(
    category: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_courses(conn, current_user["id"], category=category)

@router.get("/recommended", response_model=list[CourseSummary])
def recommended(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """Catalog ranked by overlap with the learner's resolved topics."""
    prefs = prefs_repo.get(conn, current_user["id"]) or {}
    profile = users_repo.get_profile(conn, current_user)
    topics = query_builder.resolve_topics(
        preference_topics=prefs.get("topics"),
        profile=profile,
        user_type=current_user.get("user_type"),
        max_topics=8,
    )
    return repo.recommend_courses(conn, current_user["id"], topics)

@router.get("/me", response_model=list[EnrollmentOut])
def my_courses(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_enrollments(conn, current_user["id"])

@router.get("/{public_id}", response_model=CourseDetail)
def course_detail(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    course = repo.get_course_detail(conn, current_user["id"], public_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course

@router.get("/{public_id}/topics", response_model=CourseTopicsOut)
def course_topics(
    public_id: str,
    module: str | None = Query(None, description="Limit to one module's lessons"),
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    out = repo.course_topics(conn, public_id, module)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return out

# ── enrollment + progress ──────────────────────────────────────────────────────
@router.post("/{public_id}/enroll", response_model=EnrollmentOut)
def enroll(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    enr = repo.enroll(conn, current_user["id"], public_id)
    if enr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return enr

@router.post("/lessons/{lesson_public_id}/complete", response_model=EnrollmentOut)
def complete_lesson(
    lesson_public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    enr = repo.mark_lesson_complete(conn, current_user["id"], lesson_public_id)
    if enr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found, or you are not enrolled in its course",
        )
    return enr

# ── certificates ────────────────────────────────────────────────────────────────
@certificates_router.get("/me", response_model=list[CertificateOut])
def my_certificates(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_certificates(conn, current_user["id"])

@certificates_router.get("/verify/{public_id}", response_class=HTMLResponse)
def verify_certificate(
    public_id: str,
    conn: psycopg.Connection = Depends(get_conn),
) -> HTMLResponse:
    """Public, unauthenticated certificate page (shareable / printable)."""
    cert = repo.get_certificate(conn, public_id)
    if cert is None:
        return HTMLResponse(_not_found_html(), status_code=status.HTTP_404_NOT_FOUND)
    return HTMLResponse(_certificate_html(cert))

# ── certificate HTML (self-contained, no asset pipeline) ─────────────────────────
def _certificate_html(cert: dict) -> str:
    revoked = cert.get("revoked_at") is not None
    learner = escape(cert.get("learner_name") or "Learner")
    course = escape(cert.get("course_title") or "Course")
    serial = escape(cert.get("serial") or "")
    issued = cert["issued_at"].strftime("%B %d, %Y") if cert.get("issued_at") else ""
    banner = (
        '<div class="revoked">⚠ This certificate has been revoked.</div>' if revoked else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Certificate · {serial}</title>
<style>
  :root {{ --ink:#1f2340; --muted:#6b7090; --gold:#b8862f; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:linear-gradient(135deg,#eef0ff,#fde9f3); font-family:Georgia,"Times New Roman",serif;
         color:var(--ink); padding:32px; }}
  .cert {{ width:100%; max-width:820px; background:#fffdf8; border:2px solid var(--gold);
          box-shadow:0 24px 60px rgba(40,30,80,.18); border-radius:14px; padding:56px 64px;
          position:relative; text-align:center; }}
  .cert::after {{ content:""; position:absolute; inset:14px; border:1px solid #e6d4a8; border-radius:8px;
          pointer-events:none; }}
  .eyebrow {{ letter-spacing:.32em; text-transform:uppercase; font-size:13px; color:var(--gold);
          font-family:Arial,sans-serif; margin-bottom:8px; }}
  h1 {{ font-size:40px; margin:0 0 28px; letter-spacing:.04em; }}
  .lead {{ color:var(--muted); font-size:15px; font-family:Arial,sans-serif; }}
  .name {{ font-size:34px; margin:14px 0; border-bottom:1px solid #e6d4a8; display:inline-block;
          padding:0 24px 8px; }}
  .course {{ font-size:22px; margin:10px 0 30px; }}
  .meta {{ display:flex; justify-content:space-between; margin-top:40px; font-family:Arial,sans-serif;
          font-size:13px; color:var(--muted); }}
  .meta b {{ display:block; color:var(--ink); font-size:14px; margin-top:4px; }}
  .revoked {{ background:#fdecec; color:#a12; border:1px solid #f3c2c2; padding:10px 16px;
          border-radius:8px; font-family:Arial,sans-serif; margin-bottom:20px; }}
  @media print {{ body {{ background:#fff; padding:0; }} .cert {{ box-shadow:none; }} }}
</style></head>
<body><div class="cert">
  {banner}
  <div class="eyebrow">Certificate of Completion</div>
  <h1>Journey</h1>
  <div class="lead">This is to certify that</div>
  <div class="name">{learner}</div>
  <div class="lead">has successfully completed</div>
  <div class="course">{course}</div>
  <div class="meta">
    <span>Certificate ID<b>{serial}</b></span>
    <span>Issued<b>{issued}</b></span>
  </div>
</div></body></html>"""

def _not_found_html() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Not found</title></head>"
        "<body style='font-family:system-ui;text-align:center;padding:80px;color:#444'>"
        "<h1>Certificate not found</h1><p>This certificate ID is not valid.</p></body></html>"
    )
