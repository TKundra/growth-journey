"""MCQ generation: topics (+ optional studied-material grounding) → validated MCQs.

The LLM is constrained to a JSON schema (``QuizGeneration``) via ``parse()``, but
models still miscount options or point ``correct_index`` out of range — so every
question is validated here and malformed ones are dropped rather than trusted.
Generation runs on the ``cheap`` tier (bulk MCQ work, per docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from app.ai_core.llm import get_llm
from app.core.logging import get_logger
from app.modules.assessments.schemas import GeneratedQuestion, QuizGeneration

logger = get_logger(__name__)

# Ask for 4 options; accept 2–6 so a slightly-off model isn't wholesale rejected.
_OPTIONS_TARGET = 4
_MIN_OPTIONS, _MAX_OPTIONS = 2, 6

_SYSTEM = (
    "You are an exam-question author. Write clear, unambiguous multiple-choice "
    "questions that test real understanding (not trivia or trick wording). "
    f"Each question MUST have exactly {_OPTIONS_TARGET} answer options, exactly ONE "
    "correct. `correct_index` is the 0-based index of the correct option. Provide a "
    "one- to two-sentence `explanation` of why the correct option is right. Spread "
    "the correct option across positions — don't always make it the first. "
    "Respond with ONLY the JSON object matching the schema — no prose, no code fences."
)

def _prompt(
    topics: list[str], *, difficulty: str, num_questions: int, context: list[str]
) -> str:
    lines = [
        f"Generate {num_questions} multiple-choice questions at {difficulty} difficulty.",
        f"Cover these topics (spread questions across them): {', '.join(topics)}.",
        f"Set each question's `topic` to the one it tests and `difficulty` to '{difficulty}'.",
    ]
    if context:
        lines += [
            "",
            "Ground the questions in the material the learner has been studying "
            "(use it for scope/emphasis; do NOT quote it verbatim):",
        ]
        lines += [f"- {c}" for c in context]
    return "\n".join(lines)

def _clean(q: GeneratedQuestion, *, fallback_difficulty: str) -> GeneratedQuestion | None:
    """Validate one generated question; return a normalized copy or None to drop."""
    stem = (q.stem or "").strip()
    options = [o.strip() for o in (q.options or []) if o and o.strip()]
    # drop duplicate options (case-insensitive) while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for o in options:
        if o.lower() not in seen:
            seen.add(o.lower())
            deduped.append(o)
    options = deduped
    if not stem or not (_MIN_OPTIONS <= len(options) <= _MAX_OPTIONS):
        return None
    if not (0 <= q.correct_index < len(options)):
        return None
    return GeneratedQuestion(
        stem=stem,
        options=options,
        correct_index=q.correct_index,
        explanation=(q.explanation or "").strip(),
        topic=(q.topic or "").strip(),
        difficulty=(q.difficulty or fallback_difficulty).strip() or fallback_difficulty,
    )

# The cheap tier is non-deterministic: most calls return clean MCQs, but it
# occasionally emits a shape that survives JSON parsing yet fails per-question
# validation, leaving zero usable questions. One retry turns that rare empty
# result into a success without escalating cost/latency on the common path.
_MAX_ATTEMPTS = 2

def _attempt(
    topics: list[str], *, difficulty: str, num_questions: int, context: list[str]
) -> list[GeneratedQuestion]:
    result = get_llm().parse(
        _prompt(topics, difficulty=difficulty, num_questions=num_questions, context=context),
        QuizGeneration,
        tier="cheap",
        system=_SYSTEM,
    )
    cleaned = [
        c
        for q in result.questions
        if (c := _clean(q, fallback_difficulty=difficulty)) is not None
    ]
    dropped = len(result.questions) - len(cleaned)
    if dropped:
        logger.warning("generate: dropped %d malformed question(s)", dropped)
    return cleaned

def generate(
    topics: list[str],
    *,
    difficulty: str = "beginner",
    num_questions: int = 5,
    context: list[str] | None = None,
) -> list[GeneratedQuestion]:
    """LLM-generate validated MCQs for the given topics. Returns [] if nothing usable.

    `context` is optional grounding (e.g. titles/summaries of the learner's studied
    material). Raises LLMNotConfigured if no OLLAMA_API_KEY (router maps to 503)."""
    if not topics:
        return []
    cleaned: list[GeneratedQuestion] = []
    for attempt in range(_MAX_ATTEMPTS):
        cleaned = _attempt(
            topics, difficulty=difficulty, num_questions=num_questions, context=context or []
        )
        if cleaned:
            break
        if attempt + 1 < _MAX_ATTEMPTS:
            logger.warning("generate: no usable questions; retrying (attempt %d)", attempt + 2)
    return cleaned[:num_questions]
