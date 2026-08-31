from datetime import datetime, UTC
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from quiz_shared.enums import (
    LanguageLevel,
    MediaType,
    QuestionType,
    QuizCategory,
    CourseLevel,
    UserRole,
)

__all__ = [
    "CourseLevel",
    "LanguageLevel",
    "MediaType",
    "QuestionType",
    "QuizCategory",
    "UserRole",
    "User",
    "QuizQuestion",
    "Quiz",
    "QuizMedia",
    "Question",
    "QuestionMedia",
    "QuizAttempt",
    "Answer",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _tz_datetime_column(*, onupdate: bool = False) -> Column:
    """A PostgreSQL timezone-aware timestamp column.

    ``sqlmodel`` compiles a plain ``datetime`` field to a naive
    ``TIMESTAMP WITHOUT TIME ZONE`` column, which asyncpg rejects when the
    bound value is tz-aware (as our ``datetime.now(UTC)`` defaults are). Using
    ``DateTime(timezone=True)`` keeps every stored timestamp consistent.
    """
    kwargs: dict[str, Any] = {"default": _utcnow}
    if onupdate:
        kwargs["onupdate"] = _utcnow
    return Column(DateTime(timezone=True), **kwargs)

# -------------------------
# Users
# -------------------------

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    level: CourseLevel
    role: UserRole = Field(default=UserRole.STUDENT)

    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column())

    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(onupdate=True),
    )

    attempts: list["QuizAttempt"] = Relationship(back_populates="user")

# -------------------------
# Quiz -> Question mapping
# -------------------------

class QuizQuestion(SQLModel, table=True):
    __tablename__ = "quiz_questions"

    quiz_id: UUID = Field(
        foreign_key="quizzes.id",
        primary_key=True,
    )

    question_id: UUID = Field(
        foreign_key="questions.id",
        primary_key=True,
    )

    position: int = 0

    quiz: "Quiz" = Relationship(sa_relationship_kwargs={"overlaps": "questions,quizzes"})
    question: "Question" = Relationship(sa_relationship_kwargs={"overlaps": "questions,quizzes"})

# -------------------------
# Quiz
# -------------------------

class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    title: str
    description: str | None = None

    category: QuizCategory = QuizCategory.READING
    level: LanguageLevel = LanguageLevel.A1

    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column())
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column(onupdate=True))

    questions: list["Question"] = Relationship(
        back_populates="quizzes",
        link_model=QuizQuestion,
    )

    attempts: list["QuizAttempt"] = Relationship(back_populates="quiz")

    media: list["QuizMedia"] = Relationship(back_populates="quiz")

    def __str__(self) -> str:
        return self.title


# -------------------------
# Quiz media
# -------------------------
# Shared context for the whole quiz (e.g. a reading passage or listening
# audio clip that every question refers to) — distinct from QuestionMedia,
# which is a per-question illustration (e.g. a vocabulary quiz's per-word
# image). Both can be used on the same quiz; neither implies the other.

class QuizMedia(SQLModel, table=True):
    __tablename__ = "quiz_media"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    quiz_id: UUID = Field(
        foreign_key="quizzes.id",
        index=True,
    )

    type: MediaType
    url: str | None = None
    caption: str | None = None
    position: int = 0

    quiz: Quiz = Relationship(back_populates="media")

# -------------------------
# Question
# -------------------------

class Question(SQLModel, table=True):
    __tablename__ = "questions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    type: QuestionType

    prompt: str

    suggested_score: float = 1.0

    config: dict = Field(sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column())

    media: list["QuestionMedia"] = Relationship(back_populates="question")

    quizzes: list["Quiz"] = Relationship(
        back_populates="questions",
        link_model=QuizQuestion,
    )

    answers: list["Answer"] = Relationship(back_populates="question")

    def __str__(self) -> str:
        return self.prompt[:60] + "…" if len(self.prompt) > 60 else self.prompt

# -------------------------
# Media
# -------------------------

class QuestionMedia(SQLModel, table=True):
    __tablename__ = "question_media"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    question_id: UUID = Field(
        foreign_key="questions.id",
        index=True,
    )

    type: MediaType
    url: str | None = None
    caption: str | None = None
    position: int = 0

    question: Question = Relationship(back_populates="media")

# -------------------------
# Quiz Attempt
# -------------------------

class QuizAttempt(SQLModel, table=True):
    __tablename__ = "quiz_attempts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    quiz_id: UUID = Field(
        foreign_key="quizzes.id",
        index=True,
    )

    user_id: UUID = Field(
        foreign_key="users.id",
        index=True,
    )

    started_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column())
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    score: float | None = None

    user: User = Relationship(back_populates="attempts")

    quiz: "Quiz" = Relationship(back_populates="attempts")

    answers: list["Answer"] = Relationship(
        back_populates="attempt",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
    })


# -------------------------
# Answers
# -------------------------

class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "question_id",
            name="uq_answer_per_question",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    attempt_id: UUID = Field(
        foreign_key="quiz_attempts.id",
        index=True,
    )

    question_id: UUID = Field(
        foreign_key="questions.id",
        index=True,
    )

    response: dict = Field(sa_column=Column(JSON))

    is_correct: bool | None = None

    points_awarded: float = 0

    answered_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_datetime_column())

    question: Question = Relationship(back_populates="answers")

    attempt: QuizAttempt = Relationship(back_populates="answers")
