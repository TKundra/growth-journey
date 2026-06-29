"""Assessment routes: generate a quiz, take it, submit for deterministic scoring,
review the result, and see per-topic progress.

Flow: GET preferences + profile → resolve topics → (optional) pull studied-material
context → LLM generate MCQs → persist quiz → return taker view (no answer key).
Submit scores selected vs correct index in the DB and reveals explanations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai_core.llm import LLMNotConfigured
from app.db import get_conn
from app.modules.assessments import generator
from app.modules.assessments import mock
from app.modules.assessments import mock_repository as mock_repo
from app.modules.assessments import repository as repo
from app.modules.assessments.schemas import (
    AttemptResult,
    GenerateMockTestIn,
    GenerateQuizIn,
    MockReport,
    MockTestOut,
    MockTestSummary,
    QuizOut,
    QuizSummary,
    StatsOut,
    SubmitMockTestIn,
    SubmitQuizIn,
)
from app.modules.auth.deps import get_current_user
from app.modules.courses import repository as courses_repo
from app.modules.preferences import repository as prefs_repo
from app.modules.study_material import query_builder
from app.modules.users import repository as users_repo

import psycopg

router = APIRouter(prefix="/assessments", tags=["assessments"])

_NO_LLM = "AI is not configured (set OLLAMA_API_KEY) — quiz generation is unavailable."

@router.post("/quizzes/generate", response_model=QuizOut)
def generate_quiz(
    body: GenerateQuizIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    prefs = prefs_repo.get(conn, current_user["id"]) or {}
    profile = users_repo.get_profile(conn, current_user)

    difficulty = body.difficulty or prefs.get("difficulty") or "beginner"
    # "Quiz me on this course": the syllabus topics join the explicit overrides.
    overrides = list(body.topics)
    if body.course_id:
        ct = courses_repo.course_topics(
            conn, str(body.course_id), str(body.module_id) if body.module_id else None
        )
        if ct:
            overrides += ct["topics"]
    topics = query_builder.resolve_topics(
        preference_topics=prefs.get("topics"),
        profile=profile,
        user_type=current_user.get("user_type"),
        overrides=overrides,
        max_topics=body.max_topics,
    )
    if not topics:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No topics to quiz on. Set preferences/profile or pass `topics`.",
        )

    # Best-effort grounding in what the learner has actually been reading.
    context = repo.topic_material(conn, current_user["id"], topics)
    try:
        questions = generator.generate(
            topics, difficulty=difficulty, num_questions=body.num_questions, context=context
        )
    except LLMNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_LLM)

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model returned no usable questions. Try again or narrow the topics.",
        )

    title = f"{topics[0]} quiz" if len(topics) == 1 else f"{topics[0]} & more"
    return repo.create_quiz(
        conn,
        current_user["id"],
        title=title,
        difficulty=difficulty,
        topics=topics,
        questions=questions,
    )

@router.get("/quizzes", response_model=list[QuizSummary])
def list_quizzes(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return repo.list_quizzes(conn, current_user["id"])

@router.get("/stats", response_model=StatsOut)
def stats(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    return repo.stats(conn, current_user["id"])

@router.get("/quizzes/{public_id}", response_model=QuizOut)
def get_quiz(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    quiz = repo.get_quiz(conn, current_user["id"], public_id)
    if quiz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz

@router.post("/quizzes/{public_id}/submit", response_model=AttemptResult)
def submit_quiz(
    public_id: str,
    body: SubmitQuizIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    key = repo.answer_key(conn, current_user["id"], public_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    chosen = {str(a.question_id): a.selected_index for a in body.answers}
    scored: list[dict] = []
    answers_out: list[dict] = []
    for q in key["questions"]:
        sel = chosen.get(str(q["public_id"]))
        is_correct = sel is not None and sel == q["correct_index"]
        scored.append({"question_id": q["id"], "selected_index": sel, "is_correct": is_correct})
        answers_out.append(
            {
                "question_id": q["public_id"],
                "stem": q["stem"],
                "options": q["options"],
                "selected_index": sel,
                "correct_index": q["correct_index"],
                "is_correct": is_correct,
                "explanation": q["explanation"],
            }
        )

    attempt = repo.record_attempt(
        conn, quiz_id=key["quiz_id"], user_id=current_user["id"], scored=scored
    )
    total = attempt["total"]
    return {
        "public_id": attempt["public_id"],
        "quiz_id": key["quiz_public_id"],
        "score": attempt["score"],
        "total": total,
        "percentage": round(100.0 * attempt["score"] / total, 1) if total else 0.0,
        "submitted_at": attempt["submitted_at"],
        "answers": answers_out,
    }

@router.get("/quizzes/{public_id}/result", response_model=AttemptResult)
def quiz_result(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    result = repo.latest_attempt(conn, current_user["id"], public_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No attempt found for this quiz"
        )
    total = result["total"]
    result["percentage"] = round(100.0 * result["score"] / total, 1) if total else 0.0
    return result

# ── mock tests (Phase 6) ──────────────────────────────────────────────────────
_NO_MOCK_Q = (
    "The model returned no usable questions for any section. "
    "Try again or adjust the topics."
)

@router.post("/mock-tests/generate", response_model=MockTestOut)
def generate_mock_test(
    body: GenerateMockTestIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Generate a full-length, sectional mock test on demand. Sections are taken
    from the request, or auto-built from the learner's resolved topics."""
    prefs = prefs_repo.get(conn, current_user["id"]) or {}
    profile = users_repo.get_profile(conn, current_user)
    difficulty = body.difficulty or prefs.get("difficulty") or "intermediate"

    default_topics = query_builder.resolve_topics(
        preference_topics=prefs.get("topics"),
        profile=profile,
        user_type=current_user.get("user_type"),
        overrides=list(body.topics),
        max_topics=max(body.num_sections, 4),
    )
    if not default_topics and not any(s.topics for s in body.sections):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No topics for the mock test. Set preferences/profile, pass `topics`, "
            "or give each section its own topics.",
        )

    try:
        test = mock.generate(
            conn, current_user["id"], body, default_topics=default_topics, difficulty=difficulty
        )
    except LLMNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_LLM)
    if test is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_NO_MOCK_Q)
    return test

@router.get("/mock-tests", response_model=list[MockTestSummary])
def list_mock_tests(
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    return mock_repo.list_mock_tests(conn, current_user["id"])

@router.get("/mock-tests/{public_id}", response_model=MockTestOut)
def get_mock_test(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Taker view (resume). Opening an unstarted, unsubmitted test starts its clock."""
    test = mock_repo.get_mock_test(conn, current_user["id"], public_id, for_taking=True)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock test not found")
    return test

@router.post("/mock-tests/{public_id}/submit", response_model=MockReport)
def submit_mock_test(
    public_id: str,
    body: SubmitMockTestIn,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """Score the single submission and return the full report. A mock test can be
    submitted only once."""
    key = mock_repo.answer_key(conn, current_user["id"], public_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock test not found")
    if key["submitted_at"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This mock test has already been submitted.",
        )

    chosen = {str(a.question_id): a for a in body.answers}
    scored = []
    for q in key["questions"]:
        a = chosen.get(str(q["public_id"]))
        sel = a.selected_index if a else None
        scored.append(
            {
                "question_id": q["id"],
                "selected_index": sel,
                "is_correct": sel is not None and sel == q["correct_index"],
                "time_ms": a.time_ms if a else None,
            }
        )
    mock_repo.record_submission(conn, mock_test_id=key["mock_test_id"], scored=scored)
    return mock_repo.report(conn, current_user["id"], public_id)

@router.get("/mock-tests/{public_id}/report", response_model=MockReport)
def mock_test_report(
    public_id: str,
    current_user: dict = Depends(get_current_user),
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    result = mock_repo.report(conn, current_user["id"], public_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No submitted mock test found for this id",
        )
    return result
