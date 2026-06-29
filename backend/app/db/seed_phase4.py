"""Seed Phase 4: an admin user + our own published courses.

Idempotent — re-runnable. The admin is upserted by email; courses go through
`courses.repository.upsert_course` (matched by slug), so running twice refreshes
rather than duplicates. These hand-authored courses are the concrete model an
org-data ETL job will later transform into (same CourseUpsertIn shape).

Run:  python -m app.db.seed_phase4
Env:  SEED_ADMIN_EMAIL (default admin@journey.app), SEED_ADMIN_PASSWORD (default admin12345)
"""

from __future__ import annotations

import os

from app.core.security import hash_password
from app.db.pool import get_pool
from app.modules.courses import repository as courses_repo
from app.modules.courses.schemas import CourseUpsertIn, LessonUpsertIn, ModuleUpsertIn


def _ensure_admin(conn) -> dict:
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@journey.app").lower()
    password = os.getenv("SEED_ADMIN_PASSWORD", "admin12345")
    row = conn.execute(
        """
        insert into users (email, password_hash, full_name, role, is_email_verified, user_type)
        values (%s, %s, %s, 'admin', true, 'professional')
        on conflict (email) do update set role = 'admin', is_email_verified = true
        returning id, email, role
        """,
        (email, hash_password(password), "Journey Admin"),
    ).fetchone()
    conn.commit()
    return row


# ── our own courses (catalog seed) ──────────────────────────────────────────────
COURSES: list[CourseUpsertIn] = [
    CourseUpsertIn(
        slug="python-for-data",
        title="Python for Data Analysis",
        subtitle="From zero to confident with pandas & NumPy",
        description=(
            "A hands-on path into data work with Python: the language essentials, "
            "wrangling tabular data with pandas, and turning numbers into insight."
        ),
        level="beginner",
        category="Data",
        tags=["python", "pandas", "numpy", "data analysis"],
        emoji="🐍",
        est_minutes=420,
        is_published=True,
        modules=[
            ModuleUpsertIn(
                title="Python foundations",
                summary="The core language you need before touching data.",
                lessons=[
                    LessonUpsertIn(
                        title="Values, variables & types",
                        content="Numbers, strings, booleans, and how Python names values.",
                        topics=["python basics", "data types"],
                        est_minutes=30,
                    ),
                    LessonUpsertIn(
                        title="Lists, dicts & comprehensions",
                        content="The collections you'll use constantly in data code.",
                        topics=["python collections", "comprehensions"],
                        est_minutes=40,
                    ),
                ],
            ),
            ModuleUpsertIn(
                title="Wrangling data with pandas",
                summary="Load, clean and reshape real datasets.",
                lessons=[
                    LessonUpsertIn(
                        title="Series & DataFrames",
                        content="pandas' two core structures and how to index them.",
                        topics=["pandas", "dataframes"],
                        est_minutes=45,
                    ),
                    LessonUpsertIn(
                        title="Cleaning & transforming",
                        content="Missing values, types, joins and group-by.",
                        topics=["data cleaning", "pandas groupby"],
                        est_minutes=50,
                    ),
                ],
            ),
        ],
    ),
    CourseUpsertIn(
        slug="system-design-basics",
        title="System Design Fundamentals",
        subtitle="Scale, reliability and the building blocks",
        description=(
            "Learn how large systems are put together: caching, load balancing, "
            "databases and the trade-offs behind every architecture decision."
        ),
        level="intermediate",
        category="Engineering",
        tags=["system design", "scalability", "caching", "load balancing", "databases"],
        emoji="🏗️",
        est_minutes=360,
        is_published=True,
        modules=[
            ModuleUpsertIn(
                title="Scaling the basics",
                summary="The first levers you pull when traffic grows.",
                lessons=[
                    LessonUpsertIn(
                        title="Load balancing",
                        content="Spreading requests across servers; strategies and health checks.",
                        topics=["load balancing", "horizontal scaling"],
                        est_minutes=40,
                    ),
                    LessonUpsertIn(
                        title="Caching",
                        content="Where to cache, eviction policies, and invalidation.",
                        topics=["caching", "redis", "cache invalidation"],
                        est_minutes=45,
                    ),
                ],
            ),
            ModuleUpsertIn(
                title="Data at scale",
                summary="Storing and querying data as you grow.",
                lessons=[
                    LessonUpsertIn(
                        title="SQL vs NoSQL",
                        content="Picking a datastore by access pattern and consistency needs.",
                        topics=["databases", "sql", "nosql"],
                        est_minutes=45,
                    ),
                    LessonUpsertIn(
                        title="Replication & sharding",
                        content="Surviving failure and spreading load across nodes.",
                        topics=["replication", "sharding"],
                        est_minutes=50,
                    ),
                ],
            ),
        ],
    ),
    CourseUpsertIn(
        slug="quant-aptitude",
        title="Quantitative Aptitude Crash Course",
        subtitle="Speed math for placements & competitive exams",
        description=(
            "Sharpen the quantitative skills tested in placement and competitive "
            "exams: arithmetic shortcuts, number sense, and timed problem solving."
        ),
        level="beginner",
        category="Aptitude",
        tags=["aptitude", "quantitative", "arithmetic", "percentages", "competitive exams"],
        emoji="🧮",
        est_minutes=240,
        is_published=True,
        modules=[
            ModuleUpsertIn(
                title="Arithmetic essentials",
                summary="The bread-and-butter topics that show up everywhere.",
                lessons=[
                    LessonUpsertIn(
                        title="Percentages",
                        content="Fast percentage conversions, increase/decrease, applications.",
                        topics=["percentages", "arithmetic"],
                        est_minutes=35,
                    ),
                    LessonUpsertIn(
                        title="Ratio & proportion",
                        content="Comparing quantities and scaling them reliably.",
                        topics=["ratio and proportion", "arithmetic"],
                        est_minutes=35,
                    ),
                ],
            ),
            ModuleUpsertIn(
                title="Time, speed & work",
                summary="Classic word-problem families and the shortcuts.",
                lessons=[
                    LessonUpsertIn(
                        title="Time, speed & distance",
                        content="Relative speed, averages, and the standard setups.",
                        topics=["time speed distance", "word problems"],
                        est_minutes=40,
                    ),
                    LessonUpsertIn(
                        title="Time & work",
                        content="Work rates, pipes & cisterns, and combined effort.",
                        topics=["time and work", "word problems"],
                        est_minutes=40,
                    ),
                ],
            ),
        ],
    ),
]


def main() -> None:
    with get_pool().connection() as conn:
        admin = _ensure_admin(conn)
        print(f"admin: {admin['email']} (role={admin['role']})")
        for c in COURSES:
            detail = courses_repo.upsert_course(conn, admin["id"], c)
            print(
                f"course: {detail['slug']} — {detail['module_count']} modules, "
                f"{detail['lesson_count']} lessons (published={detail['is_published']})"
            )
    print("seed complete.")


if __name__ == "__main__":
    main()
