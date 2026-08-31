"""Shared, plain-BaseModel read shapes for API responses.

These mirror the backend's ``app.schemas.*Read``/``Token`` classes but carry
no SQLModel/ORM dependency, so both the FastAPI backend and the Flet frontend
import the same source of truth for what the wire format looks like.
Write-path (Create/Update) schemas stay backend-local since the frontend
never constructs them.

``from_attributes=True`` matches SQLModel's own default (which the backend
relied on implicitly), so these can still be built directly from ORM rows via
``SomeRead.model_validate(row)``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from quiz_shared.enums import (
    CourseLevel,
    LanguageLevel,
    MediaType,
    QuestionType,
    QuizCategory,
    UserRole,
)


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MediaRead(_Base):
    id: UUID
    question_id: UUID
    type: MediaType
    url: str | None = None
    caption: str | None = None
    position: int = 0


class QuestionRead(_Base):
    id: UUID
    type: QuestionType
    prompt: str
    suggested_score: float = 1.0
    config: dict = {}
    created_at: datetime
    media: list[MediaRead] = []


class QuizMediaRead(_Base):
    id: UUID
    quiz_id: UUID
    type: MediaType
    url: str | None = None
    caption: str | None = None
    position: int = 0


class QuizRead(_Base):
    id: UUID
    title: str
    description: str | None = None
    category: QuizCategory
    level: LanguageLevel
    created_at: datetime
    updated_at: datetime
    question_ids: list[UUID] = []
    media: list[QuizMediaRead] = []


class AnswerRead(_Base):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    response: dict = {}
    is_correct: bool | None = None
    points_awarded: float = 0.0
    answered_at: datetime


class AttemptRead(_Base):
    id: UUID
    quiz_id: UUID
    user_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    score: float | None = None
    max_score: float


class UserRead(_Base):
    id: UUID
    email: EmailStr
    level: CourseLevel
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenRead(_Base):
    access_token: str
    token_type: str = "bearer"


class AdminAttemptRow(_Base):
    attempt_id: UUID
    user_id: UUID
    email: EmailStr
    level: CourseLevel
    score: float | None = None
    max_score: float
    finished: bool
    finished_at: datetime | None = None


class QuestionStatRow(_Base):
    question_id: UUID
    prompt: str
    correct_count: int
    incorrect_count: int
    unanswered_count: int
