"""Raw-SQL data access for the quiz engine (questions, quizzes, attempts).

psycopg3 binds Python lists to Postgres arrays directly, so `options text[]` round
-trips as a list with no JSON layer. The answer key (`correct_index`/`explanation`)
is only ever read by the scoring/result paths — taker-facing reads omit it.
"""

from __future__ import annotations

import psycopg

from app.modules.assessments.schemas import GeneratedQuestion

# ── grounding context ─────────────────────────────────────────────────────────
def topic_material(
    conn: psycopg.Connection, user_id: int, topics: list[str], *, limit: int = 8
) -> list[str]:
    """"title — summary" strings from the user's feed for the given topics, to
    ground generation in what they've actually been studying. Best-effort: empty
    if they have no matching material yet."""
    if not topics:
        return []
    rows = conn.execute(
        """
        select res.title, res.summary
        from feed_items f
        join resources res on res.id = f.resource_id
        where f.user_id = %s and lower(f.topic) = any(%s)
        order by f.relevance desc nulls last, f.created_at desc
        limit %s
        """,
        (user_id, [t.lower() for t in topics], limit),
    ).fetchall()
    out: list[str] = []
    for r in rows:
        title = (r["title"] or "").strip()
        summary = (r["summary"] or "").strip()
        if title:
            out.append(f"{title} — {summary}" if summary else title)
    return out

# ── quiz creation ─────────────────────────────────────────────────────────────
def create_quiz(
    conn: psycopg.Connection,
    user_id: int,
    *,
    title: str,
    difficulty: str,
    topics: list[str],
    questions: list[GeneratedQuestion],
) -> dict:
    """Persist the question bank + quiz + ordered membership in one transaction.
    Returns the taker-facing quiz dict (no answer key)."""
    quiz = conn.execute(
        """
        insert into quizzes (user_id, title, difficulty, topics)
        values (%s, %s, %s, %s)
        returning id, public_id, title, difficulty, topics, created_at
        """,
        (user_id, title, difficulty, topics),
    ).fetchone()

    out_questions: list[dict] = []
    for pos, q in enumerate(questions):
        qrow = conn.execute(
            """
            insert into questions
                (created_by, topic, difficulty, stem, options, correct_index, explanation)
            values (%s, %s, %s, %s, %s, %s, %s)
            returning public_id, topic, difficulty, stem, options
            """,
            (user_id, q.topic, q.difficulty, q.stem, q.options, q.correct_index, q.explanation),
        ).fetchone()
        conn.execute(
            "insert into quiz_questions (quiz_id, question_id, position) "
            "select %s, id, %s from questions where public_id = %s",
            (quiz["id"], pos, qrow["public_id"]),
        )
        out_questions.append(qrow)
    conn.commit()
    return {
        "public_id": quiz["public_id"],
        "title": quiz["title"],
        "difficulty": quiz["difficulty"],
        "topics": quiz["topics"],
        "num_questions": len(out_questions),
        "created_at": quiz["created_at"],
        "questions": out_questions,
    }

# ── reads ─────────────────────────────────────────────────────────────────────
def get_quiz(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    """Taker view: quiz + ordered questions WITHOUT the answer key."""
    quiz = conn.execute(
        """
        select id, public_id, title, difficulty, topics, created_at
        from quizzes where public_id = %s and user_id = %s
        """,
        (public_id, user_id),
    ).fetchone()
    if quiz is None:
        return None
    questions = conn.execute(
        """
        select q.public_id, q.topic, q.difficulty, q.stem, q.options
        from quiz_questions qq
        join questions q on q.id = qq.question_id
        where qq.quiz_id = %s
        order by qq.position
        """,
        (quiz["id"],),
    ).fetchall()
    return {
        "public_id": quiz["public_id"],
        "title": quiz["title"],
        "difficulty": quiz["difficulty"],
        "topics": quiz["topics"],
        "num_questions": len(questions),
        "created_at": quiz["created_at"],
        "questions": questions,
    }

def answer_key(conn: psycopg.Connection, user_id: int, public_id: str) -> dict | None:
    """Scoring view: quiz internal id + every question with its correct_index and
    explanation, keyed by question public_id. None if the quiz isn't the user's."""
    quiz = conn.execute(
        "select id, public_id from quizzes where public_id = %s and user_id = %s",
        (public_id, user_id),
    ).fetchone()
    if quiz is None:
        return None
    rows = conn.execute(
        """
        select q.id, q.public_id, q.stem, q.options, q.correct_index, q.explanation
        from quiz_questions qq
        join questions q on q.id = qq.question_id
        where qq.quiz_id = %s
        order by qq.position
        """,
        (quiz["id"],),
    ).fetchall()
    return {"quiz_id": quiz["id"], "quiz_public_id": quiz["public_id"], "questions": rows}

def list_quizzes(conn: psycopg.Connection, user_id: int, *, limit: int = 50) -> list[dict]:
    """Quiz history with attempt count + best score (no questions embedded)."""
    return conn.execute(
        """
        select z.public_id, z.title, z.difficulty, z.topics, z.created_at,
               (select count(*) from quiz_questions qq where qq.quiz_id = z.id) as num_questions,
               (select count(*) from attempts a where a.quiz_id = z.id) as attempt_count,
               (select max(a.score) from attempts a where a.quiz_id = z.id) as best_score
        from quizzes z
        where z.user_id = %s
        order by z.created_at desc
        limit %s
        """,
        (user_id, limit),
    ).fetchall()

# ── attempts ──────────────────────────────────────────────────────────────────
def record_attempt(
    conn: psycopg.Connection,
    *,
    quiz_id: int,
    user_id: int,
    scored: list[dict],
) -> dict:
    """Persist a scored attempt + its per-question answers. `scored` items carry
    question internal id, selected_index, is_correct."""
    score = sum(1 for s in scored if s["is_correct"])
    attempt = conn.execute(
        """
        insert into attempts (quiz_id, user_id, score, total)
        values (%s, %s, %s, %s)
        returning id, public_id, score, total, submitted_at
        """,
        (quiz_id, user_id, score, len(scored)),
    ).fetchone()
    for s in scored:
        conn.execute(
            "insert into attempt_answers (attempt_id, question_id, selected_index, is_correct) "
            "values (%s, %s, %s, %s)",
            (attempt["id"], s["question_id"], s["selected_index"], s["is_correct"]),
        )
    conn.commit()
    return attempt

def latest_attempt(conn: psycopg.Connection, user_id: int, quiz_public_id: str) -> dict | None:
    """Most recent attempt for a quiz with full per-question results (incl. answer
    key + explanations — the learner has submitted, so it's safe to reveal)."""
    quiz = conn.execute(
        "select id, public_id from quizzes where public_id = %s and user_id = %s",
        (quiz_public_id, user_id),
    ).fetchone()
    if quiz is None:
        return None
    attempt = conn.execute(
        """
        select id, public_id, score, total, submitted_at
        from attempts where quiz_id = %s and user_id = %s
        order by submitted_at desc limit 1
        """,
        (quiz["id"], user_id),
    ).fetchone()
    if attempt is None:
        return None
    answers = conn.execute(
        """
        select q.public_id as question_id, q.stem, q.options, q.correct_index,
               q.explanation, aa.selected_index, aa.is_correct
        from attempt_answers aa
        join questions q on q.id = aa.question_id
        join quiz_questions qq on qq.question_id = q.id and qq.quiz_id = %s
        where aa.attempt_id = %s
        order by qq.position
        """,
        (quiz["id"], attempt["id"]),
    ).fetchall()
    return {
        "public_id": attempt["public_id"],
        "quiz_id": quiz["public_id"],
        "score": attempt["score"],
        "total": attempt["total"],
        "submitted_at": attempt["submitted_at"],
        "answers": answers,
    }

# ── analytics ─────────────────────────────────────────────────────────────────
def stats(conn: psycopg.Connection, user_id: int) -> dict:
    """Per-topic + overall accuracy over all the user's answered questions."""
    rows = conn.execute(
        """
        select coalesce(nullif(q.topic, ''), 'General') as topic,
               count(*) as answered,
               count(*) filter (where aa.is_correct) as correct
        from attempt_answers aa
        join attempts a on a.id = aa.attempt_id
        join questions q on q.id = aa.question_id
        where a.user_id = %s
        group by 1
        order by answered desc, topic
        """,
        (user_id,),
    ).fetchall()
    per_topic = [
        {
            "topic": r["topic"],
            "answered": r["answered"],
            "correct": r["correct"],
            "accuracy": round(100.0 * r["correct"] / r["answered"], 1) if r["answered"] else 0.0,
        }
        for r in rows
    ]
    answered = sum(r["answered"] for r in per_topic)
    correct = sum(r["correct"] for r in per_topic)
    return {
        "answered": answered,
        "correct": correct,
        "accuracy": round(100.0 * correct / answered, 1) if answered else 0.0,
        "per_topic": per_topic,
    }
