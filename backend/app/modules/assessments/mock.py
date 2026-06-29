"""Mock-test orchestration: turn a generation request into a sectional, timed
test by reusing the Phase 3 MCQ generator once per section.

Sections come either from the request (explicit `sections`) or, in auto mode,
from the learner's resolved topics (one section per topic). Each section is
generated independently and grounded in that section's studied material; a
section that yields no usable questions is dropped rather than left empty.
"""

from __future__ import annotations

import psycopg

from app.core.logging import get_logger
from app.modules.assessments import generator
from app.modules.assessments import mock_repository as mock_repo
from app.modules.assessments import repository as quiz_repo
from app.modules.assessments.schemas import GenerateMockTestIn

logger = get_logger(__name__)

# A formal mock budgets roughly a minute per question when no limit is given.
_SECONDS_PER_QUESTION = 60

def _section_specs(body: GenerateMockTestIn, default_topics: list[str]) -> list[dict]:
    """Resolve the requested sections (explicit, else auto-built from topics)."""
    if body.sections:
        specs: list[dict] = []
        for s in body.sections:
            topics = [t.strip() for t in s.topics if t and t.strip()] or default_topics
            specs.append(
                {
                    "title": s.title.strip() or (topics[0] if topics else "Section"),
                    "topics": topics,
                    "num_questions": s.num_questions,
                    "duration_minutes": s.duration_minutes,
                }
            )
        return specs
    # auto: one section per resolved topic, capped at num_sections
    return [
        {
            "title": t,
            "topics": [t],
            "num_questions": body.questions_per_section,
            "duration_minutes": None,
        }
        for t in default_topics[: body.num_sections]
    ]

def _default_title(sections: list[dict]) -> str:
    first = sections[0]["title"] if sections else "Full-length"
    return f"{first} mock test" if len(sections) == 1 else f"{first} & more — mock test"

def generate(
    conn: psycopg.Connection,
    user_id: int,
    body: GenerateMockTestIn,
    *,
    default_topics: list[str],
    difficulty: str,
) -> dict | None:
    """Generate + persist a mock test. Returns the taker view, or None if no
    section produced any usable questions."""
    sections: list[dict] = []
    for spec in _section_specs(body, default_topics):
        if not spec["topics"]:
            continue
        context = quiz_repo.topic_material(conn, user_id, spec["topics"])
        questions = generator.generate(
            spec["topics"],
            difficulty=difficulty,
            num_questions=spec["num_questions"],
            context=context,
        )
        if not questions:
            logger.warning("mock: section %r produced no questions; dropping", spec["title"])
            continue
        duration = (
            spec["duration_minutes"] * 60
            if spec["duration_minutes"]
            else len(questions) * _SECONDS_PER_QUESTION
        )
        sections.append(
            {
                "title": spec["title"],
                "topics": spec["topics"],
                "duration_seconds": duration,
                "questions": questions,
            }
        )

    if not sections:
        return None

    overall = (
        body.duration_minutes * 60
        if body.duration_minutes
        else sum(s["duration_seconds"] for s in sections)
    )
    # union of section topics, order-preserving, for listing/percentile cohorting
    seen: set[str] = set()
    topics_union: list[str] = []
    for s in sections:
        for t in s["topics"]:
            if t.lower() not in seen:
                seen.add(t.lower())
                topics_union.append(t)

    return mock_repo.create_mock_test(
        conn,
        user_id,
        title=body.title or _default_title(sections),
        difficulty=difficulty,
        topics=topics_union,
        duration_seconds=overall,
        sections=sections,
    )
