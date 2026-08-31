"""Answer grading for quiz questions.

Per-type config/response shapes and grading rules live in
:mod:`app.core.question_types`; this module wires an attempt's response to
the matching handler.
"""

from typing import Any

from app.core.question_types import HANDLERS, parse_config
from app.models import Question

GRADE_SCALE = 10.0
"""Every quiz's reported score/max_score is rescaled onto 0-``GRADE_SCALE``,
regardless of how many questions it has or how their ``suggested_score``
weights are authored, so grades read consistently across quizzes."""


def grade_question(question: Question, response: dict[str, Any]) -> bool:
    handler = HANDLERS.get(question.type)
    if handler is None:
        return False
    config = parse_config(question)
    if config is None:
        return False
    return handler.grade(config, response)


def normalize_score(
    raw_score: float | None, raw_max: float, scale: float = GRADE_SCALE
) -> float | None:
    """Rescale a raw point-based score onto a fixed 0-``scale`` grading scale.

    Returns ``None`` unchanged (an unfinished attempt has no score yet).
    A quiz with no gradable points (``raw_max <= 0``) normalizes to ``0.0``
    rather than dividing by zero.
    """
    if raw_score is None:
        return None
    if raw_max <= 0:
        return 0.0
    return round(raw_score / raw_max * scale, 2)


def normalized_max_score(raw_max: float, scale: float = GRADE_SCALE) -> float:
    """The display max_score paired with :func:`normalize_score` — always
    ``scale`` for a gradable quiz, or ``0.0`` for one with no gradable points."""
    return scale if raw_max > 0 else 0.0
