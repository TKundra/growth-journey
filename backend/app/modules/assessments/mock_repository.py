"""Raw-SQL data access for formal mock tests (Phase 6).

Mirrors the quiz repository but for the sectional, single-submission mock model:
mock_tests → mock_sections → mock_questions (reusing the shared `questions` bank)
+ mock_answers. Scoring is deterministic and DB-side; the report derives section
scores, a percentile against same-difficulty peers, time analysis and weak areas.
"""

from __future__ import annotations

import psycopg

from app.modules.assessments.schemas import GeneratedQuestion

# A topic below this accuracy (%) in a single test is flagged as a weak area.
_WEAK_THRESHOLD = 60.0

# ── creation ──────────────────────────────────────────────────────────────────
def create_mock_test(
    conn: psycopg.Connection,
    user_id: int,
    *,
    title: str,
    difficulty: str,
    topics: list[str],
    duration_seconds: int,
    sections: list[dict],
) -> dict:
    """Persist the test + its sections + the generated question bank in one
    transaction. `sections` items: {title, topics, duration_seconds, questions:
    [GeneratedQuestion]}. Returns the taker view (no answer key, timer not started)."""
    total_questions = sum(len(s["questions"]) for s in sections)
    test = conn.execute(
        """
        insert into mock_tests
            (user_id, title, difficulty, topics, duration_seconds, total_questions)
        values (%s, %s, %s, %s, %s, %s)
        returning id, public_id
        """,
        (user_id, title, difficulty, topics, duration_seconds, total_questions),
    ).fetchone()

    for s_pos, section in enumerate(sections):
        srow = conn.execute(
            """
            insert into mock_sections (mock_test_id, position, title, topics, duration_seconds)
            values (%s, %s, %s, %s, %s)
            returning id
            """,
            (test["id"], s_pos, section["title"], section["topics"], section["duration_seconds"]),
        ).fetchone()
        for q_pos, q in enumerate(section["questions"]):
            qrow = conn.execute(
                """
                insert into questions
                    (created_by, topic, difficulty, stem, options, correct_index, explanation)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (user_id, q.topic, q.difficulty, q.stem, q.options, q.correct_index, q.explanation),
            ).fetchone()
            conn.execute(
                "insert into mock_questions (mock_section_id, question_id, position) "
                "values (%s, %s, %s)",
                (srow["id"], qrow["id"], q_pos),
            )
    conn.commit()
    return get_mock_test(conn, user_id, str(test["public_id"]), for_taking=False)

# ── taker view ────────────────────────────────────────────────────────────────
def get_mock_test(
    conn: psycopg.Connection, user_id: int, public_id: str, *, for_taking: bool
) -> dict | None:
    """The sectional taker view (no answer key). When `for_taking` and the test is
    unsubmitted and not yet started, lazily stamp `started_at` — opening a mock to
    take it starts its clock."""
    test = conn.execute(
        """
        select id, public_id, title, difficulty, topics, duration_seconds,
               total_questions, started_at, submitted_at, created_at
        from mock_tests where public_id = %s and user_id = %s
        """,
        (public_id, user_id),
    ).fetchone()
    if test is None:
        return None
    if for_taking and test["submitted_at"] is None and test["started_at"] is None:
        started = conn.execute(
            "update mock_tests set started_at = now() where id = %s returning started_at",
            (test["id"],),
        ).fetchone()
        conn.commit()
        test["started_at"] = started["started_at"]

    sections = conn.execute(
        """
        select id, public_id, position, title, topics, duration_seconds
        from mock_sections where mock_test_id = %s order by position
        """,
        (test["id"],),
    ).fetchall()
    out_sections = []
    for s in sections:
        questions = conn.execute(
            """
            select q.public_id, q.topic, q.difficulty, q.stem, q.options
            from mock_questions mq
            join questions q on q.id = mq.question_id
            where mq.mock_section_id = %s
            order by mq.position
            """,
            (s["id"],),
        ).fetchall()
        out_sections.append(
            {
                "public_id": s["public_id"],
                "position": s["position"],
                "title": s["title"],
                "topics": s["topics"],
                "duration_seconds": s["duration_seconds"],
                "questions": questions,
            }
        )
    return {
        "public_id": test["public_id"],
        "title": test["title"],
        "difficulty": test["difficulty"],
        "topics": test["topics"],
        "duration_seconds": test["duration_seconds"],
        "total_questions": test["total_questions"],
        "started_at": test["started_at"],
        "submitted_at": test["submitted_at"],
        "created_at": test["created_at"],
        "sections": out_sections,
    }

def list_mock_tests(conn: psycopg.Connection, user_id: int, *, limit: int = 50) -> list[dict]:
    """Mock-test history with a derived status + score percentage."""
    return conn.execute(
        """
        select public_id, title, difficulty, total_questions, duration_seconds,
               score, created_at, submitted_at,
               case
                 when submitted_at is not null then 'submitted'
                 when started_at  is not null then 'in_progress'
                 else 'created'
               end as status,
               case when submitted_at is not null and total_questions > 0
                    then round(100.0 * score / total_questions, 1) end as percentage
        from mock_tests
        where user_id = %s
        order by created_at desc
        limit %s
        """,
        (user_id, limit),
    ).fetchall()

# ── scoring ───────────────────────────────────────────────────────────────────
def answer_key(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    """Scoring view: the test's internal id + submission state + every question's
    correct_index, keyed for submit. None if the test isn't the user's."""
    test = conn.execute(
        "select id, public_id, submitted_at from mock_tests where public_id = %s and user_id = %s",
        (public_id, user_id),
    ).fetchone()
    if test is None:
        return None
    rows = conn.execute(
        """
        select q.id, q.public_id, q.correct_index
        from mock_sections ms
        join mock_questions mq on mq.mock_section_id = ms.id
        join questions q on q.id = mq.question_id
        where ms.mock_test_id = %s
        order by ms.position, mq.position
        """,
        (test["id"],),
    ).fetchall()
    return {
        "mock_test_id": test["id"],
        "public_id": test["public_id"],
        "submitted_at": test["submitted_at"],
        "questions": rows,
    }

def record_submission(
    conn: psycopg.Connection, *, mock_test_id: int, scored: list[dict]
) -> None:
    """Persist the single attempt's answers and stamp the test submitted. `scored`
    items: {question_id, selected_index, is_correct, time_ms}."""
    score = sum(1 for s in scored if s["is_correct"])
    for s in scored:
        conn.execute(
            """
            insert into mock_answers (mock_test_id, question_id, selected_index, is_correct, time_ms)
            values (%s, %s, %s, %s, %s)
            """,
            (mock_test_id, s["question_id"], s["selected_index"], s["is_correct"], s["time_ms"]),
        )
    conn.execute(
        "update mock_tests set score = %s, submitted_at = now() where id = %s",
        (score, mock_test_id),
    )
    conn.commit()

# ── report ────────────────────────────────────────────────────────────────────
def _percentile(conn: psycopg.Connection, difficulty: str, percentage: float) -> float | None:
    """Where this score sits among submitted tests of the same difficulty: the %
    of that cohort scoring at or below it (includes this test, so a lone test → 100)."""
    row = conn.execute(
        """
        select count(*) as n,
               count(*) filter (
                 where total_questions > 0 and 100.0 * score / total_questions <= %s
               ) as le
        from mock_tests
        where difficulty = %s and submitted_at is not null
        """,
        (percentage, difficulty),
    ).fetchone()
    return round(100.0 * row["le"] / row["n"], 1) if row["n"] else None

def report(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    """Full report for a submitted mock test: section scores, percentile, time
    analysis, weak areas, next-step topics, and the per-question answer key.
    None if not the user's test; the router treats unsubmitted as not-found."""
    test = conn.execute(
        """
        select id, public_id, title, difficulty, total_questions, duration_seconds,
               score, started_at, submitted_at
        from mock_tests where public_id = %s and user_id = %s
        """,
        (public_id, user_id),
    ).fetchone()
    if test is None or test["submitted_at"] is None:
        return None

    rows = conn.execute(
        """
        select ms.position as s_pos, ms.title as section_title, ms.duration_seconds,
               mq.position as q_pos, q.public_id as question_id, q.topic, q.stem,
               q.options, q.correct_index, q.explanation,
               a.selected_index, a.is_correct, a.time_ms
        from mock_sections ms
        join mock_questions mq on mq.mock_section_id = ms.id
        join questions q on q.id = mq.question_id
        left join mock_answers a on a.question_id = q.id and a.mock_test_id = ms.mock_test_id
        where ms.mock_test_id = %s
        order by ms.position, mq.position
        """,
        (test["id"],),
    ).fetchall()

    total = test["total_questions"]
    score = test["score"] or 0
    percentage = round(100.0 * score / total, 1) if total else 0.0

    # per-section + per-topic rollups, and the answer list, in one pass
    sections: dict[int, dict] = {}
    topics: dict[str, dict] = {}
    answers_out: list[dict] = []
    for r in rows:
        sec = sections.setdefault(
            r["s_pos"],
            {
                "title": r["section_title"],
                "duration_seconds": r["duration_seconds"],
                "total": 0,
                "correct": 0,
                "time_ms": 0,
                "timed": 0,
            },
        )
        sec["total"] += 1
        sec["correct"] += 1 if r["is_correct"] else 0
        if r["time_ms"] is not None:
            sec["time_ms"] += r["time_ms"]
            sec["timed"] += 1

        topic = (r["topic"] or "").strip() or "General"
        ts = topics.setdefault(topic, {"answered": 0, "correct": 0})
        ts["answered"] += 1
        ts["correct"] += 1 if r["is_correct"] else 0

        answers_out.append(
            {
                "question_id": r["question_id"],
                "stem": r["stem"],
                "options": r["options"],
                "selected_index": r["selected_index"],
                "correct_index": r["correct_index"],
                "is_correct": bool(r["is_correct"]),
                "explanation": r["explanation"],
            }
        )

    section_scores = [
        {
            "title": s["title"],
            "total": s["total"],
            "correct": s["correct"],
            "accuracy": round(100.0 * s["correct"] / s["total"], 1) if s["total"] else 0.0,
            "avg_seconds_per_question": round(s["time_ms"] / s["timed"] / 1000, 1)
            if s["timed"]
            else None,
            "duration_seconds": s["duration_seconds"],
        }
        for _, s in sorted(sections.items())
    ]

    weak_areas = sorted(
        (
            {
                "topic": t,
                "answered": v["answered"],
                "correct": v["correct"],
                "accuracy": round(100.0 * v["correct"] / v["answered"], 1) if v["answered"] else 0.0,
            }
            for t, v in topics.items()
        ),
        key=lambda x: x["accuracy"],
    )
    weak_areas = [w for w in weak_areas if w["accuracy"] < _WEAK_THRESHOLD]
    next_steps = [w["topic"] for w in weak_areas[:3]]

    # time analysis: prefer summed per-question timings, else the clock span
    timed_total_ms = sum(r["time_ms"] for r in rows if r["time_ms"] is not None)
    timed_count = sum(1 for r in rows if r["time_ms"] is not None)
    time_taken = None
    if test["started_at"] is not None:
        time_taken = int((test["submitted_at"] - test["started_at"]).total_seconds())
    if timed_count:
        avg_per_q = round(timed_total_ms / timed_count / 1000, 1)
    elif time_taken is not None and total:
        avg_per_q = round(time_taken / total, 1)
    else:
        avg_per_q = None

    return {
        "public_id": test["public_id"],
        "title": test["title"],
        "difficulty": test["difficulty"],
        "score": score,
        "total": total,
        "percentage": percentage,
        "percentile": _percentile(conn, test["difficulty"], percentage),
        "submitted_at": test["submitted_at"],
        "time": {
            "duration_seconds": test["duration_seconds"],
            "time_taken_seconds": time_taken,
            "avg_seconds_per_question": avg_per_q,
        },
        "sections": section_scores,
        "weak_areas": weak_areas,
        "next_steps": next_steps,
        "answers": answers_out,
    }
