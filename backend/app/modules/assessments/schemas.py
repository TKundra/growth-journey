"""Assessment schemas: quiz-generation request, the LLM MCQ contract, and the
API-facing quiz / question / attempt shapes.

Two views of a question exist on purpose:
  * ``QuizQuestionOut`` — what a taker sees: stem + options, NO answer/explanation.
  * ``AnswerResult``    — what a submitter gets back: their choice, the correct
                          index, and the explanation.
This keeps the answer key server-side until the quiz is actually submitted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

Difficulty = Literal["beginner", "intermediate", "advanced"]

# ── generation request ───────────────────────────────────────────────────────
class GenerateQuizIn(BaseModel):
    """Optional overrides; by default we use the user's preferences + profile.

    When `course_id` is set, the course's lesson topics (optionally narrowed to
    `module_id`) are added to the override set — "quiz me on this course/module".
    """
    topics: list[str] = Field(default_factory=list, description="Override preference topics")
    course_id: UUID | None = Field(default=None, description="Quiz on this course's syllabus")
    module_id: UUID | None = Field(default=None, description="Narrow to one module of the course")
    difficulty: Difficulty | None = None
    num_questions: int = Field(default=5, ge=1, le=20)
    max_topics: int = Field(default=4, ge=1, le=8)

# ── LLM contract (what parse() validates into) ────────────────────────────────
def _resolve_index(raw: object, options: list[str]) -> int:
    """Coerce a model's "which option is correct" into a 0-based index.

    Cheap models express the answer as an int, a 1-letter label ("B"), or the
    full option text — accept all three. Returns -1 when unresolvable so the
    generator's range check drops the question rather than guessing wrong."""
    if raw is None or isinstance(raw, bool):
        return -1
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    # Exact option-text match wins first: a model that answers "4" when the options
    # are ["3","4"] means the text, not index 4 (which would be out of range).
    for i, o in enumerate(options):
        if str(o).strip().lower() == s.lower():
            return i
    if len(s) == 1 and s.isalpha():
        return ord(s.upper()) - ord("A")
    if s.lstrip("-").isdigit():
        return int(s)
    return -1

class GeneratedQuestion(BaseModel):
    stem: str = ""
    options: list[str] = Field(default_factory=list)
    # 0-based index into `options`. Kept permissive here; the generator validates
    # range + option count and drops anything malformed (models miscount).
    correct_index: int = 0
    explanation: str = ""
    topic: str = ""
    difficulty: str = "beginner"

    @model_validator(mode="before")
    @classmethod
    def _normalize_keys(cls, data: object) -> object:
        """Map the alternate field names cheap models emit onto our schema."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "stem" not in d:
            for k in ("question", "prompt", "text", "q"):
                if d.get(k):
                    d["stem"] = d[k]
                    break
        if "options" not in d:
            for k in ("choices", "answers", "option_list"):
                if d.get(k):
                    d["options"] = d[k]
                    break
        opts = d.get("options") or []
        # options sometimes arrive as a dict keyed by label, e.g. {"A": "...", "B": "..."}.
        # Take the values in order — a letter answer then resolves by position (A→0).
        if isinstance(opts, dict):
            opts = list(opts.values())
            d["options"] = opts
        # ...or as a list of objects [{text/label/value: "..."}]
        elif opts and isinstance(opts[0], dict):
            opts = [o.get("text") or o.get("label") or o.get("value") or "" for o in opts]
            d["options"] = opts
        if "correct_index" not in d or not isinstance(d.get("correct_index"), int):
            raw = next(
                (
                    d[k]
                    for k in (
                        "correct_index", "answer_index", "correct_option",
                        "correct", "answer", "correct_answer",
                    )
                    if d.get(k) is not None
                ),
                None,
            )
            d["correct_index"] = _resolve_index(raw, opts if isinstance(opts, list) else [])
        return d

class QuizGeneration(BaseModel):
    questions: list[GeneratedQuestion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: object) -> object:
        """Accept a bare array of questions, or an object under a differently named
        key — cheap models often skip the {"questions": [...]} wrapper."""
        if isinstance(data, list):
            return {"questions": data}
        if isinstance(data, dict) and "questions" not in data:
            for k in ("items", "mcqs", "quiz", "data", "results"):
                if isinstance(data.get(k), list):
                    return {"questions": data[k]}
        return data

# ── API outputs ──────────────────────────────────────────────────────────────
class QuizQuestionOut(BaseModel):
    """Taker's view — deliberately omits the correct answer and explanation."""
    public_id: UUID
    topic: str
    difficulty: str
    stem: str
    options: list[str]

class QuizOut(BaseModel):
    public_id: UUID
    title: str
    difficulty: str
    topics: list[str] = Field(default_factory=list)
    num_questions: int
    created_at: datetime
    questions: list[QuizQuestionOut] = Field(default_factory=list)

class QuizSummary(BaseModel):
    """One row in the learner's quiz history (no questions embedded)."""
    public_id: UUID
    title: str
    difficulty: str
    topics: list[str] = Field(default_factory=list)
    num_questions: int
    created_at: datetime
    attempt_count: int = 0
    best_score: int | None = None

# ── submission + scoring ──────────────────────────────────────────────────────
class SubmittedAnswer(BaseModel):
    question_id: UUID
    selected_index: int | None = None  # None = left blank

class SubmitQuizIn(BaseModel):
    answers: list[SubmittedAnswer] = Field(default_factory=list)

class AnswerResult(BaseModel):
    question_id: UUID
    stem: str
    options: list[str]
    selected_index: int | None = None
    correct_index: int
    is_correct: bool
    explanation: str = ""

class AttemptResult(BaseModel):
    public_id: UUID
    quiz_id: UUID
    score: int
    total: int
    percentage: float
    submitted_at: datetime
    answers: list[AnswerResult] = Field(default_factory=list)

# ── progress analytics ────────────────────────────────────────────────────────
class TopicStat(BaseModel):
    topic: str
    answered: int
    correct: int
    accuracy: float  # 0..100

class StatsOut(BaseModel):
    answered: int
    correct: int
    accuracy: float
    per_topic: list[TopicStat] = Field(default_factory=list)
