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
from app.modules.assessments import repository as repo
from app.modules.assessments.schemas import (
    AttemptResult,
    GenerateQuizIn,
    QuizOut,
    QuizSummary,
    StatsOut,
    SubmitQuizIn,
)
from app.modules.auth.deps import get_current_user
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
    topics = query_builder.resolve_topics(
        preference_topics=prefs.get("topics"),
        profile=profile,
        user_type=current_user.get("user_type"),
        overrides=body.topics,
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
