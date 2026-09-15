from uuid import UUID

from sqlmodel import SQLModel

from app.models import LanguageLevel, QuizCategory
from quiz_shared.schemas import QuizRead

__all__ = [
    "QuizBase",
    "QuizCreate",
    "QuizUpdate",
    "QuizQuestionLinkCreate",
    "QuizQuestionLink",
    "QuizRead",
    "QuizDetail",
]


class QuizBase(SQLModel):
    title: str
    description: str | None = None
    category: QuizCategory = QuizCategory.READING
    level: LanguageLevel = LanguageLevel.A1
    unit: str | None = None


class QuizCreate(QuizBase):
    pass


class QuizUpdate(SQLModel):
    title: str | None = None
    description: str | None = None
    category: QuizCategory | None = None
    level: LanguageLevel | None = None
    unit: str | None = None


class QuizQuestionLinkCreate(SQLModel):
    question_id: UUID
    position: int = 0


class QuizQuestionLink(SQLModel):
    quiz_id: UUID
    question_id: UUID
    position: int


class QuizDetail(QuizRead):
    pass
