"""Per-question-type strategy: config shapes, grading, and answer/explanation text.

Consolidates the switch-on-``question.type`` logic that used to be duplicated
between ``grading.py`` and ``pdf_report.py`` into one handler per
:class:`QuestionType`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from app.models import Question, QuestionType

# -------------------------
# Config shapes (one per QuestionType)
# -------------------------


class MultipleChoiceConfig(BaseModel):
    options: list[str]
    correct_index: int
    explanations: list[str | None] | None = None


class MultipleSelectionConfig(BaseModel):
    options: list[str]
    correct_indices: list[int]
    explanations: list[str | None] | None = None


class TrueFalseConfig(BaseModel):
    answer: bool


class ShortTextConfig(BaseModel):
    accepted_answers: list[str]


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list):
        return {_norm(v) for v in value}
    return value


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(none selected)"
    if value is None:
        return "(no answer)"
    return str(value)


# -------------------------
# Handlers
# -------------------------


class QuestionTypeHandler:
    config_model: type[BaseModel]

    def grade(self, config: BaseModel, response: dict) -> bool:
        raise NotImplementedError

    def correct_answer_text(self, config: BaseModel) -> str | None:
        raise NotImplementedError

    def explanation_text(self, config: BaseModel) -> str | None:
        return None

    def option_breakdown(self, config: BaseModel) -> list[tuple[str, bool, str | None]] | None:
        """Per-option (text, is_correct, explanation) rows, in option order.

        ``None`` means "not applicable" (e.g. true/false, short text), so
        callers fall back to ``correct_answer_text``/``explanation_text``.
        """
        return None

    def format_response(self, response: dict) -> str:
        return _format_value(response.get("selected"))


class MultipleChoiceHandler(QuestionTypeHandler):
    config_model = MultipleChoiceConfig

    def grade(self, config: MultipleChoiceConfig, response: dict) -> bool:
        try:
            correct = config.options[config.correct_index]
        except IndexError:
            return False
        return _norm(response.get("selected")) == _norm(correct)

    def correct_answer_text(self, config: MultipleChoiceConfig) -> str | None:
        try:
            return config.options[config.correct_index]
        except IndexError:
            return None

    def option_breakdown(
        self, config: MultipleChoiceConfig
    ) -> list[tuple[str, bool, str | None]]:
        explanations = config.explanations or []
        return [
            (
                option,
                i == config.correct_index,
                explanations[i] if i < len(explanations) else None,
            )
            for i, option in enumerate(config.options)
        ]


class MultipleSelectionHandler(QuestionTypeHandler):
    config_model = MultipleSelectionConfig

    def grade(self, config: MultipleSelectionConfig, response: dict) -> bool:
        try:
            correct = [config.options[i] for i in config.correct_indices]
        except IndexError:
            return False
        return _norm(response.get("selected")) == _norm(correct)

    def correct_answer_text(self, config: MultipleSelectionConfig) -> str | None:
        try:
            return ", ".join(config.options[i] for i in config.correct_indices)
        except IndexError:
            return None

    def option_breakdown(
        self, config: MultipleSelectionConfig
    ) -> list[tuple[str, bool, str | None]]:
        explanations = config.explanations or []
        correct = set(config.correct_indices)
        return [
            (
                option,
                i in correct,
                explanations[i] if i < len(explanations) else None,
            )
            for i, option in enumerate(config.options)
        ]


class TrueFalseHandler(QuestionTypeHandler):
    config_model = TrueFalseConfig

    def grade(self, config: TrueFalseConfig, response: dict) -> bool:
        return response.get("selected") == config.answer

    def correct_answer_text(self, config: TrueFalseConfig) -> str | None:
        return "True" if config.answer else "False"


class ShortTextHandler(QuestionTypeHandler):
    config_model = ShortTextConfig

    def grade(self, config: ShortTextConfig, response: dict) -> bool:
        text = _norm(response.get("text"))
        accepted = [_norm(a) for a in config.accepted_answers]
        return text in accepted

    def correct_answer_text(self, config: ShortTextConfig) -> str | None:
        return " or ".join(config.accepted_answers) if config.accepted_answers else None

    def format_response(self, response: dict) -> str:
        return _format_value(response.get("text"))


HANDLERS: dict[QuestionType, QuestionTypeHandler] = {
    QuestionType.MULTIPLE_CHOICE: MultipleChoiceHandler(),
    QuestionType.MULTIPLE_SELECTION: MultipleSelectionHandler(),
    QuestionType.TRUE_FALSE: TrueFalseHandler(),
    QuestionType.SHORT_TEXT: ShortTextHandler(),
}


# Config keys that give away the answer. Everything here is needed by grading
# (which reads the ORM row directly) and by the PDF report, but must not be
# handed to a student before they answer.
ANSWER_KEY_FIELDS = frozenset(
    {
        "correct_index",  # multiple_choice
        "correct_indices",  # multiple_selection
        "answer",  # true_false
        "accepted_answers",  # short_text
        "explanations",  # multiple choice/selection, per option
    }
)


def public_config(config: dict | None) -> dict:
    """``config`` with the answer key removed.

    ``GET /api/v1/questions/{id}`` is public, and returned the whole config —
    so the correct answer and its explanations reached the browser before the
    question was answered. Only ``options`` is actually needed to render a
    question, and grading compares option *text* rather than an index, so
    dropping these keys costs the student UI nothing.
    """
    return {k: v for k, v in (config or {}).items() if k not in ANSWER_KEY_FIELDS}


def parse_config(question: Question) -> BaseModel | None:
    """Validate ``question.config`` against its type's shape.

    Returns ``None`` on malformed/pre-existing bad data instead of raising, so
    callers (grading, PDF export, ...) can degrade gracefully.
    """
    handler = HANDLERS.get(question.type)
    if handler is None:
        return None
    try:
        return handler.config_model.model_validate(question.config or {})
    except ValidationError:
        return None
