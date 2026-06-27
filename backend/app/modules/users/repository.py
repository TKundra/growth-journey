"""Raw-SQL data access for profiles.

A user has at most one profile, matching ``users.user_type``. Switching type
removes the other branch's row so the two never coexist.
"""

from __future__ import annotations

import psycopg

from app.modules.users.schemas import ProfessionalProfileIn, StudentProfileIn

# Note: column is `job_role` ("role" is reserved SQL); aliased to `role` for the API.
_PROF_COLS = "public_id, experience_years, job_role as role, industry, skills, goal, updated_at"
_STUDENT_COLS = (
    "public_id, education_level, stream, subjects, target_exams, preferred_colleges, updated_at"
)

def upsert_professional(
    conn: psycopg.Connection, user_id: int, data: ProfessionalProfileIn
) -> dict:
    conn.execute("update users set user_type = 'professional' where id = %s", (user_id,))
    conn.execute("delete from profiles_student where user_id = %s", (user_id,))
    row = conn.execute(
        f"""
        insert into profiles_professional
            (user_id, experience_years, job_role, industry, skills, goal)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (user_id) do update set
            experience_years = excluded.experience_years,
            job_role         = excluded.job_role,
            industry         = excluded.industry,
            skills           = excluded.skills,
            goal             = excluded.goal
        returning {_PROF_COLS}
        """,
        (user_id, data.experience_years, data.role, data.industry, data.skills, data.goal),
    ).fetchone()
    conn.commit()
    return row

def upsert_student(conn: psycopg.Connection, user_id: int, data: StudentProfileIn) -> dict:
    conn.execute("update users set user_type = 'student' where id = %s", (user_id,))
    conn.execute("delete from profiles_professional where user_id = %s", (user_id,))
    row = conn.execute(
        f"""
        insert into profiles_student
            (user_id, education_level, stream, subjects, target_exams, preferred_colleges)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (user_id) do update set
            education_level    = excluded.education_level,
            stream             = excluded.stream,
            subjects           = excluded.subjects,
            target_exams       = excluded.target_exams,
            preferred_colleges = excluded.preferred_colleges
        returning {_STUDENT_COLS}
        """,
        (
            user_id,
            data.education_level,
            data.stream,
            data.subjects,
            data.target_exams,
            data.preferred_colleges,
        ),
    ).fetchone()
    conn.commit()
    return row

def get_profile(conn: psycopg.Connection, user: dict) -> dict | None:
    """Fetch the profile row matching the user's type (None if not set yet)."""
    if user["user_type"] == "professional":
        return conn.execute(
            f"select {_PROF_COLS} from profiles_professional where user_id = %s",
            (user["id"],),
        ).fetchone()
    if user["user_type"] == "student":
        return conn.execute(
            f"select {_STUDENT_COLS} from profiles_student where user_id = %s",
            (user["id"],),
        ).fetchone()
    return None
