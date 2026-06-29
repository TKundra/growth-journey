"""Raw-SQL data access for courses, enrollments and certificates.

Two surfaces:
  * Learner — published catalog, enrollment, per-lesson mark-complete (which
    deterministically recomputes progress and issues a certificate at 100%),
    and topic aggregation for study/quiz linking.
  * Admin — idempotent course authoring (the same path an ETL import uses),
    publish toggles, enrollment oversight, certificate revocation.

Progress is denormalized onto `enrollments` and recomputed DB-side on every
mark-complete — the single source of truth, exactly like quiz scoring.
"""

from __future__ import annotations

import psycopg

from app.modules.courses.schemas import CourseUpsertIn

# Catalog summary columns + per-user enrollment overlay. `e` is the current user's
# enrollment row (left-joined), so is_enrolled/progress/status come for free.
_COURSE_SUMMARY = """
    c.public_id, c.slug, c.title, c.subtitle, c.level, c.category, c.tags,
    c.emoji, c.est_minutes, c.is_published,
    (select count(*) from course_modules m where m.course_id = c.id) as module_count,
    (select count(*) from course_lessons l
       join course_modules m on m.id = l.module_id
       where m.course_id = c.id) as lesson_count,
    (e.id is not null) as is_enrolled,
    coalesce(e.progress, 0) as progress,
    e.status as status
"""

# ── catalog (learner) ──────────────────────────────────────────────────────────
def list_courses(
    conn: psycopg.Connection, user_id: int, *, category: str | None = None, limit: int = 60
) -> list[dict]:
    where = "c.is_published = true"
    params: list = [user_id]
    if category:
        where += " and lower(c.category) = lower(%s)"
        params.append(category)
    params.append(limit)
    return conn.execute(
        f"""
        select {_COURSE_SUMMARY}
        from courses c
        left join enrollments e on e.course_id = c.id and e.user_id = %s
        where {where}
        order by c.created_at desc
        limit %s
        """,
        params,
    ).fetchall()

def recommend_courses(
    conn: psycopg.Connection, user_id: int, topics: list[str], *, limit: int = 8
) -> list[dict]:
    """Published courses the user is NOT enrolled in, ranked by overlap between
    their topics and the course's tags / category / lesson topics. With no topics,
    falls back to most-recent published."""
    lowered = [t.lower() for t in topics if t]
    if not lowered:
        rows = conn.execute(
            f"""
            select {_COURSE_SUMMARY}
            from courses c
            left join enrollments e on e.course_id = c.id and e.user_id = %s
            where c.is_published = true and e.id is null
            order by c.created_at desc
            limit %s
            """,
            (user_id, limit),
        ).fetchall()
        return rows
    rows = conn.execute(
        f"""
        select {_COURSE_SUMMARY},
            (
              (select count(*) from unnest(c.tags) t where lower(t) = any(%s))
              + (case when lower(c.category) = any(%s) then 1 else 0 end)
              + (select count(distinct lower(t))
                   from course_lessons l
                   join course_modules m on m.id = l.module_id, unnest(l.topics) t
                   where m.course_id = c.id and lower(t) = any(%s))
            ) as match_score
        from courses c
        left join enrollments e on e.course_id = c.id and e.user_id = %s
        where c.is_published = true and e.id is null
        order by match_score desc, c.created_at desc
        limit %s
        """,
        (lowered, lowered, lowered, user_id, limit),
    ).fetchall()
    return [r for r in rows if r.get("match_score", 0) > 0] or rows

def get_course_detail(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    """Full syllabus tree + the user's progress overlay. Published-only for learners."""
    course = conn.execute(
        f"""
        select {_COURSE_SUMMARY}, c.description, c.id as _cid, e.id as _eid
        from courses c
        left join enrollments e on e.course_id = c.id and e.user_id = %s
        where c.public_id = %s and c.is_published = true
        """,
        (user_id, public_id),
    ).fetchone()
    if course is None:
        return None
    cid = course.pop("_cid")
    eid = course.pop("_eid")  # enrollment id (None if not enrolled) → drives is_completed
    course["modules"] = _modules_tree(conn, cid, eid)
    return course

def _modules_tree(conn: psycopg.Connection, course_id: int, enrollment_id: int | None) -> list[dict]:
    modules = conn.execute(
        """
        select id, public_id, position, title, summary
        from course_modules where course_id = %s order by position
        """,
        (course_id,),
    ).fetchall()
    for m in modules:
        mid = m.pop("id")
        m["lessons"] = conn.execute(
            """
            select l.public_id, l.position, l.title, l.content, l.topics, l.est_minutes,
                   exists (
                     select 1 from lesson_progress lp
                     where lp.lesson_id = l.id and lp.enrollment_id = %s
                   ) as is_completed
            from course_lessons l
            where l.module_id = %s
            order by l.position
            """,
            (enrollment_id, mid),
        ).fetchall()
    return modules

# ── enrollment + progress (learner) ─────────────────────────────────────────────
def enroll(conn: psycopg.Connection, user_id: int, course_public_id: str) -> dict | None:
    """Enroll (idempotent). Returns the enrollment overlay, or None if the course
    isn't a published course."""
    course = conn.execute(
        "select id from courses where public_id = %s and is_published = true",
        (course_public_id,),
    ).fetchone()
    if course is None:
        return None
    conn.execute(
        """
        insert into enrollments (user_id, course_id) values (%s, %s)
        on conflict (user_id, course_id) do nothing
        """,
        (user_id, course["id"]),
    )
    conn.commit()
    return get_enrollment(conn, user_id, course_public_id)

def list_enrollments(conn: psycopg.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        f"""
        select e.public_id as _enr_pid, e.status, e.progress, e.enrolled_at, e.completed_at,
               e.id as _eid, {_COURSE_SUMMARY}
        from enrollments e
        join courses c on c.id = e.course_id
        where e.user_id = %s
        order by e.enrolled_at desc
        """,
        (user_id,),
    ).fetchall()
    return [_split_enrollment(conn, r) for r in rows]

def get_enrollment(
    conn: psycopg.Connection, user_id: int, course_public_id: str
) -> dict | None:
    row = conn.execute(
        f"""
        select e.public_id as _enr_pid, e.status, e.progress, e.enrolled_at, e.completed_at,
               e.id as _eid, {_COURSE_SUMMARY}
        from enrollments e
        join courses c on c.id = e.course_id
        where e.user_id = %s and c.public_id = %s
        """,
        (user_id, course_public_id),
    ).fetchone()
    return _split_enrollment(conn, row) if row else None

def _split_enrollment(conn: psycopg.Connection, row: dict) -> dict:
    """Reshape a flat enrollment+course row into the nested EnrollmentOut dict."""
    eid = row.pop("_eid")
    enr = {
        "public_id": row.pop("_enr_pid"),
        "status": row.pop("status"),
        "progress": row.pop("progress"),
        "enrolled_at": row.pop("enrolled_at"),
        "completed_at": row.pop("completed_at"),
        "course": row,  # remaining keys are exactly the CourseSummary shape
        "certificate": _certificate_for_enrollment(conn, eid),
    }
    return enr

def mark_lesson_complete(
    conn: psycopg.Connection, user_id: int, lesson_public_id: str
) -> dict | None:
    """Mark a lesson done for the user's enrollment, recompute progress, and issue
    a certificate when every lesson is complete. Returns the enrollment overlay,
    or None if the lesson is unknown / the user isn't enrolled in its course."""
    loc = conn.execute(
        """
        select l.id as lesson_id, m.course_id, c.public_id as course_public_id
        from course_lessons l
        join course_modules m on m.id = l.module_id
        join courses c on c.id = m.course_id
        where l.public_id = %s
        """,
        (lesson_public_id,),
    ).fetchone()
    if loc is None:
        return None
    enr = conn.execute(
        "select id from enrollments where user_id = %s and course_id = %s",
        (user_id, loc["course_id"]),
    ).fetchone()
    if enr is None:
        return None  # must enroll before progressing
    enrollment_id = enr["id"]

    conn.execute(
        """
        insert into lesson_progress (enrollment_id, lesson_id) values (%s, %s)
        on conflict (enrollment_id, lesson_id) do nothing
        """,
        (enrollment_id, loc["lesson_id"]),
    )

    counts = conn.execute(
        """
        select
          (select count(*) from course_lessons l
             join course_modules m on m.id = l.module_id
             where m.course_id = %s) as total,
          (select count(*) from lesson_progress lp where lp.enrollment_id = %s) as done
        """,
        (loc["course_id"], enrollment_id),
    ).fetchone()
    total, done = counts["total"], counts["done"]
    progress = round(done * 100 / total) if total else 0
    completed = total > 0 and done >= total

    conn.execute(
        """
        update enrollments set
          progress = %s,
          status = case when %s then 'completed' else 'active' end,
          completed_at = case when %s then coalesce(completed_at, now()) else null end
        where id = %s
        """,
        (progress, completed, completed, enrollment_id),
    )
    if completed:
        # serial is human-facing; enrollment id (internal) is fine to embed there.
        conn.execute(
            """
            insert into certificates (enrollment_id, serial)
            values (%s, 'JNY-' || to_char(now(), 'YYYY') || '-' || lpad(%s::text, 6, '0'))
            on conflict (enrollment_id) do nothing
            """,
            (enrollment_id, enrollment_id),
        )
    conn.commit()
    return get_enrollment(conn, user_id, loc["course_public_id"])

# ── topics for study/quiz linking ──────────────────────────────────────────────
def course_topics(
    conn: psycopg.Connection, course_public_id: str, module_public_id: str | None = None
) -> dict | None:
    """Distinct lesson topics across a course (or a single module within it).
    Returned as the override set for study-material / quiz generation."""
    course = conn.execute(
        "select id, public_id from courses where public_id = %s", (course_public_id,)
    ).fetchone()
    if course is None:
        return None
    if module_public_id:
        rows = conn.execute(
            """
            select distinct unnest(l.topics) as topic
            from course_lessons l
            join course_modules m on m.id = l.module_id
            where m.course_id = %s and m.public_id = %s
            """,
            (course["id"], module_public_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select distinct unnest(l.topics) as topic
            from course_lessons l
            join course_modules m on m.id = l.module_id
            where m.course_id = %s
            """,
            (course["id"],),
        ).fetchall()
    topics = [r["topic"] for r in rows if r["topic"]]
    return {
        "course_id": course["public_id"],
        "module_id": module_public_id,
        "topics": topics,
    }

# ── certificates ────────────────────────────────────────────────────────────────
def _certificate_for_enrollment(conn: psycopg.Connection, enrollment_id: int) -> dict | None:
    return conn.execute(
        """
        select public_id, serial, issued_at, revoked_at
        from certificates where enrollment_id = %s
        """,
        (enrollment_id,),
    ).fetchone()

def get_certificate(conn: psycopg.Connection, public_id: str) -> dict | None:
    """Public verification lookup — joins through to the course title + learner
    name. No user scoping: certificates are publicly verifiable by their id."""
    return conn.execute(
        """
        select cert.public_id, cert.serial, cert.issued_at, cert.revoked_at,
               co.title as course_title, u.full_name as learner_name
        from certificates cert
        join enrollments e on e.id = cert.enrollment_id
        join courses co on co.id = e.course_id
        join users u on u.id = e.user_id
        where cert.public_id = %s
        """,
        (public_id,),
    ).fetchone()

def list_certificates(conn: psycopg.Connection, user_id: int) -> list[dict]:
    return conn.execute(
        """
        select cert.public_id, cert.serial, cert.issued_at, cert.revoked_at,
               co.title as course_title, u.full_name as learner_name
        from certificates cert
        join enrollments e on e.id = cert.enrollment_id
        join courses co on co.id = e.course_id
        join users u on u.id = e.user_id
        where e.user_id = %s
        order by cert.issued_at desc
        """,
        (user_id,),
    ).fetchall()

# ── admin authoring (== ETL import path) ─────────────────────────────────────────
def upsert_course(conn: psycopg.Connection, admin_id: int | None, data: CourseUpsertIn) -> dict:
    """Idempotent create/replace of a course + its full module/lesson tree.

    Match key: (source, external_ref) for imports, else the unique slug. On a
    re-run the course meta is updated and the module tree is rebuilt. NOTE: a
    rebuild deletes course_lessons, which cascades lesson_progress — re-authoring
    a course resets in-flight learner progress. Acceptable while courses are
    authored before learners join; revisit if editing live courses.
    """
    existing = None
    if data.source == "import" and data.external_ref:
        existing = conn.execute(
            "select id from courses where source = 'import' and external_ref = %s",
            (data.external_ref,),
        ).fetchone()
    if existing is None:
        existing = conn.execute(
            "select id from courses where slug = %s", (data.slug,)
        ).fetchone()

    if existing:
        cid = existing["id"]
        conn.execute(
            """
            update courses set
              slug = %s, title = %s, subtitle = %s, description = %s, level = %s,
              category = %s, tags = %s, emoji = %s, est_minutes = %s,
              source = %s, external_ref = %s, is_published = %s
            where id = %s
            """,
            (
                data.slug, data.title, data.subtitle, data.description, data.level,
                data.category, data.tags, data.emoji, data.est_minutes,
                data.source, data.external_ref, data.is_published, cid,
            ),
        )
        conn.execute("delete from course_modules where course_id = %s", (cid,))
    else:
        cid = conn.execute(
            """
            insert into courses
              (slug, title, subtitle, description, level, category, tags, emoji,
               est_minutes, source, external_ref, is_published, created_by)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                data.slug, data.title, data.subtitle, data.description, data.level,
                data.category, data.tags, data.emoji, data.est_minutes,
                data.source, data.external_ref, data.is_published, admin_id,
            ),
        ).fetchone()["id"]

    for m_pos, m in enumerate(data.modules):
        mid = conn.execute(
            """
            insert into course_modules (course_id, position, title, summary)
            values (%s, %s, %s, %s) returning id
            """,
            (cid, m_pos, m.title, m.summary),
        ).fetchone()["id"]
        for l_pos, lesson in enumerate(m.lessons):
            conn.execute(
                """
                insert into course_lessons (module_id, position, title, content, topics, est_minutes)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (mid, l_pos, lesson.title, lesson.content, lesson.topics, lesson.est_minutes),
            )
    conn.commit()
    return admin_get_course(conn, conn.execute(
        "select public_id from courses where id = %s", (cid,)
    ).fetchone()["public_id"])

def admin_list_courses(conn: psycopg.Connection, *, limit: int = 200) -> list[dict]:
    """All courses incl. unpublished, with counts (no per-user overlay)."""
    return conn.execute(
        """
        select c.public_id, c.slug, c.title, c.subtitle, c.level, c.category, c.tags,
               c.emoji, c.est_minutes, c.is_published, c.source, c.external_ref, c.created_at,
               (select count(*) from course_modules m where m.course_id = c.id) as module_count,
               (select count(*) from course_lessons l
                  join course_modules m on m.id = l.module_id
                  where m.course_id = c.id) as lesson_count,
               (select count(*) from enrollments e where e.course_id = c.id) as enrollment_count
        from courses c
        order by c.created_at desc
        limit %s
        """,
        (limit,),
    ).fetchall()

def admin_get_course(conn: psycopg.Connection, public_id: str) -> dict | None:
    """Full tree for any course regardless of publish state (admin view)."""
    course = conn.execute(
        """
        select c.public_id, c.slug, c.title, c.subtitle, c.description, c.level,
               c.category, c.tags, c.emoji, c.est_minutes, c.is_published, c.source,
               c.external_ref, c.id as _cid,
               (select count(*) from course_modules m where m.course_id = c.id) as module_count,
               (select count(*) from course_lessons l
                  join course_modules m on m.id = l.module_id
                  where m.course_id = c.id) as lesson_count
        from courses c where c.public_id = %s
        """,
        (public_id,),
    ).fetchone()
    if course is None:
        return None
    cid = course.pop("_cid")
    course["is_enrolled"] = False
    course["progress"] = 0
    course["status"] = None
    course["modules"] = _modules_tree(conn, cid, None)
    return course

def set_published(conn: psycopg.Connection, public_id: str, is_published: bool) -> bool:
    cur = conn.execute(
        "update courses set is_published = %s where public_id = %s",
        (is_published, public_id),
    )
    conn.commit()
    return cur.rowcount > 0

def delete_course(conn: psycopg.Connection, public_id: str) -> bool:
    cur = conn.execute("delete from courses where public_id = %s", (public_id,))
    conn.commit()
    return cur.rowcount > 0

def admin_list_enrollments(
    conn: psycopg.Connection, *, course_public_id: str | None = None, limit: int = 500
) -> list[dict]:
    where = ""
    params: list = []
    if course_public_id:
        where = "where c.public_id = %s"
        params.append(course_public_id)
    params.append(limit)
    return conn.execute(
        f"""
        select e.public_id, e.status, e.progress, e.enrolled_at, e.completed_at,
               u.email as learner_email, u.full_name as learner_name,
               c.title as course_title, c.public_id as course_public_id
        from enrollments e
        join users u on u.id = e.user_id
        join courses c on c.id = e.course_id
        {where}
        order by e.enrolled_at desc
        limit %s
        """,
        params,
    ).fetchall()

def set_certificate_revoked(conn: psycopg.Connection, public_id: str, revoked: bool) -> bool:
    cur = conn.execute(
        "update certificates set revoked_at = case when %s then now() else null end "
        "where public_id = %s",
        (revoked, public_id),
    )
    conn.commit()
    return cur.rowcount > 0
