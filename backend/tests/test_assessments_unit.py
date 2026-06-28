"""Phase 3 unit tests — no DB, no network, no LLM.

Covers the pure pieces of the quiz engine: MCQ validation/cleanup in the
generator (the model miscounts options and points correct_index out of range in
practice, so this guardrail matters).
"""

from __future__ import annotations

from app.modules.assessments import generator
from app.modules.assessments.schemas import GeneratedQuestion, QuizGeneration


class _FakeLLM:
    def __init__(self, questions):
        self._questions = questions

    def parse(self, *_args, **_kwargs):
        return QuizGeneration(questions=self._questions)


def _gen(monkeypatch, questions, **kw):
    monkeypatch.setattr(generator, "get_llm", lambda: _FakeLLM(questions))
    return generator.generate(["Topic"], **kw)


def test_generate_empty_topics_short_circuits():
    # no LLM call needed when there's nothing to quiz on
    assert generator.generate([]) == []


def test_generate_keeps_valid_question(monkeypatch):
    q = GeneratedQuestion(
        stem="2 + 2 = ?",
        options=["3", "4", "5", "6"],
        correct_index=1,
        explanation="basic arithmetic",
        topic="Math",
    )
    out = _gen(monkeypatch, [q])
    assert len(out) == 1
    assert out[0].options[out[0].correct_index] == "4"


def test_generate_drops_out_of_range_answer(monkeypatch):
    bad = GeneratedQuestion(stem="?", options=["a", "b"], correct_index=5)
    assert _gen(monkeypatch, [bad]) == []


def test_generate_drops_too_few_options(monkeypatch):
    bad = GeneratedQuestion(stem="?", options=["only one"], correct_index=0)
    assert _gen(monkeypatch, [bad]) == []


def test_generate_drops_empty_stem(monkeypatch):
    bad = GeneratedQuestion(stem="  ", options=["a", "b"], correct_index=0)
    assert _gen(monkeypatch, [bad]) == []


def test_generate_dedupes_options_and_revalidates_index(monkeypatch):
    # duplicate options collapse; correct_index pointed at the dup-removed slot
    # would now be out of range → the question is dropped rather than mis-scored.
    q = GeneratedQuestion(stem="?", options=["a", "a", "b"], correct_index=2)
    assert _gen(monkeypatch, [q]) == []  # 3 opts → 2 after dedupe, index 2 invalid


def test_generate_dedupes_options_keeps_valid_index(monkeypatch):
    q = GeneratedQuestion(stem="?", options=["a", "A", "b", "c"], correct_index=1)
    out = _gen(monkeypatch, [q])
    assert len(out) == 1
    assert out[0].options == ["a", "b", "c"]  # case-insensitive dedupe of a/A
    # index 1 still valid and now points at "b"
    assert out[0].options[out[0].correct_index] == "b"


def test_generate_backfills_difficulty(monkeypatch):
    q = GeneratedQuestion(stem="?", options=["a", "b"], correct_index=0, difficulty="")
    out = _gen(monkeypatch, [q], difficulty="advanced")
    assert out[0].difficulty == "advanced"


def test_generate_caps_to_requested_count(monkeypatch):
    qs = [
        GeneratedQuestion(stem=f"q{i}", options=["a", "b"], correct_index=0) for i in range(10)
    ]
    out = _gen(monkeypatch, qs, num_questions=3)
    assert len(out) == 3


# ── LLM-output tolerance (cheap models ignore the strict schema) ───────────────
def test_quizgeneration_unwraps_bare_array():
    # gpt-oss:20b returns a top-level array instead of {"questions": [...]}
    raw = '[{"question": "2+2?", "options": ["3","4"], "answer": "4"}]'
    qg = QuizGeneration.model_validate_json(raw)
    assert len(qg.questions) == 1
    q = qg.questions[0]
    assert q.stem == "2+2?"  # "question" → stem
    assert q.correct_index == 1  # answer text "4" resolved to its index


def test_quizgeneration_unwraps_alternate_wrapper_key():
    qg = QuizGeneration.model_validate(
        {"mcqs": [{"stem": "?", "options": ["a", "b"], "correct_index": 0}]}
    )
    assert len(qg.questions) == 1


def test_generated_question_resolves_letter_answer():
    q = GeneratedQuestion.model_validate(
        {"question": "?", "choices": ["a", "b", "c"], "correct_option": "C"}
    )
    assert q.stem == "?" and q.options == ["a", "b", "c"]
    assert q.correct_index == 2  # "C" → index 2


def test_generated_question_options_as_dict():
    # some cheap models emit options as {"A": "...", "B": "..."} with a letter answer
    q = GeneratedQuestion.model_validate(
        {"stem": "?", "options": {"A": "red", "B": "green", "C": "blue"}, "answer": "B"}
    )
    assert q.options == ["red", "green", "blue"]
    assert q.correct_index == 1  # "B" → position 1


def test_generated_question_unresolvable_answer_is_dropped(monkeypatch):
    # answer that matches nothing → index -1 → generator drops it (never mis-scored)
    q = GeneratedQuestion.model_validate(
        {"stem": "?", "options": ["a", "b"], "answer": "totally different"}
    )
    assert q.correct_index == -1
    assert _gen(monkeypatch, [q]) == []
