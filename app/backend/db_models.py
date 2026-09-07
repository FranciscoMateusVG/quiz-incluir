from datetime import date, datetime, UTC
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
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
    "AIMonthlyBudget",
    "AIBudgetReservation",
    "AIDailyUsage",
    "VocabularyLookupGrant",
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
    kwargs: dict[str, Any] = {"default": _utcnow, "nullable": False}
    if onupdate:
        kwargs["onupdate"] = _utcnow
    return Column(DateTime(timezone=True), **kwargs)


# -------------------------
# AI spend budget
# -------------------------


class AIMonthlyBudget(SQLModel, table=True):
    __tablename__ = "ai_monthly_budgets"
    __table_args__ = (
        CheckConstraint(
            "EXTRACT(DAY FROM month_start) = 1",
            name="ck_ai_monthly_budgets_month_starts_on_day_one",
        ),
        CheckConstraint(
            "limit_microusd BETWEEN 1 AND 5000000",
            name="ck_ai_monthly_budgets_limit_range",
        ),
        CheckConstraint(
            "committed_microusd >= 0",
            name="ck_ai_monthly_budgets_committed_nonnegative",
        ),
        CheckConstraint(
            "reserved_microusd >= 0",
            name="ck_ai_monthly_budgets_reserved_nonnegative",
        ),
        CheckConstraint(
            "committed_microusd + reserved_microusd <= limit_microusd",
            name="ck_ai_monthly_budgets_within_limit",
        ),
    )

    month_start: date = Field(primary_key=True)
    limit_microusd: int = Field(sa_column=Column(BigInteger, nullable=False))
    committed_microusd: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, default=0),
    )
    reserved_microusd: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, default=0),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(onupdate=True),
    )


class AIBudgetReservation(SQLModel, table=True):
    __tablename__ = "ai_budget_reservations"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('lookup', 'pronunciation')",
            name="ck_ai_budget_reservations_operation",
        ),
        CheckConstraint(
            "state IN ('reserved', 'committed', 'released')",
            name="ck_ai_budget_reservations_state",
        ),
        CheckConstraint(
            "reserved_microusd > 0",
            name="ck_ai_budget_reservations_reserved_positive",
        ),
        CheckConstraint(
            "committed_microusd IS NULL OR committed_microusd >= 0",
            name="ck_ai_budget_reservations_committed_nonnegative",
        ),
        CheckConstraint(
            "(state = 'committed' AND committed_microusd IS NOT NULL "
            "AND committed_microusd <= reserved_microusd) OR "
            "(state IN ('reserved', 'released') AND committed_microusd IS NULL)",
            name="ck_ai_budget_reservations_state_amount_coherent",
        ),
        Index(
            "ix_ai_budget_reservations_month_state",
            "month_start",
            "state",
        ),
        Index(
            "ix_ai_budget_reservations_created_at",
            "created_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    month_start: date = Field(foreign_key="ai_monthly_budgets.month_start")
    operation: str = Field(sa_column=Column(String(32), nullable=False))
    state: str = Field(
        default="reserved",
        sa_column=Column(String(16), nullable=False, default="reserved"),
    )
    reserved_microusd: int = Field(sa_column=Column(BigInteger, nullable=False))
    committed_microusd: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(onupdate=True),
    )


class AIDailyUsage(SQLModel, table=True):
    __tablename__ = "ai_daily_usage"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('lookup', 'pronunciation')",
            name="ck_ai_daily_usage_operation",
        ),
        CheckConstraint(
            "count >= 0",
            name="ck_ai_daily_usage_count_nonnegative",
        ),
    )

    usage_date: date = Field(primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    operation: str = Field(
        sa_column=Column(String(32), primary_key=True, nullable=False),
    )
    count: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, default=0),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(onupdate=True),
    )


class VocabularyLookupGrant(SQLModel, table=True):
    __tablename__ = "vocabulary_lookup_grants"
    __table_args__ = (
        CheckConstraint(
            "char_length(translation) BETWEEN 1 AND 120",
            name="ck_vocabulary_lookup_grants_translation_length",
        ),
        Index(
            "ix_vocabulary_lookup_grants_expires_at",
            "expires_at",
        ),
        Index(
            "ix_vocabulary_lookup_grants_user_id_id",
            "user_id",
            "id",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    translation: str = Field(sa_column=Column(String(120), nullable=False))
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=_tz_datetime_column(),
    )


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
