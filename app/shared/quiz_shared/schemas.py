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
from enum import StrEnum
from typing import Annotated
from unicodedata import category, is_normalized
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
)

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


class _StrictWireBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_canonical_identity(value: str) -> str:
    """Validate a previously authenticated identity without DNS policy."""

    if any(
        ord(character) <= 0x1F
        or ord(character) == 0x7F
        or character in {"\u2028", "\u2029"}
        or category(character) == "Cf"
        for character in value
    ):
        raise ValueError("identity contains unsafe control characters")
    return value


CanonicalIdentityEmail = Annotated[
    str,
    StringConstraints(min_length=1, max_length=254),
    AfterValidator(_validate_canonical_identity),
]


def _validate_canonical_vocabulary_value(value: str) -> str:
    """Reject text that is unsafe or non-canonical at an API boundary."""

    if not value or value != value.strip() or not is_normalized("NFC", value):
        raise ValueError("value must be nonempty, unpadded Unicode NFC")
    if any(
        ord(character) <= 0x1F
        or 0x7F <= ord(character) <= 0x9F
        or character in {"\u2028", "\u2029"}
        or category(character) == "Cf"
        for character in value
    ):
        raise ValueError("value contains unsafe Unicode characters")
    return value


CanonicalVocabularyText120 = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=120),
    AfterValidator(_validate_canonical_vocabulary_value),
]
CanonicalVocabularyDefinition = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=240),
    AfterValidator(_validate_canonical_vocabulary_value),
]


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
    # This value has already been authenticated and normalized upstream by
    # BetterAuth. Response serialization must not apply deliverability policy:
    # the isolated parity fixture deliberately uses the reserved .test TLD.
    email: CanonicalIdentityEmail
    level: CourseLevel
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenRead(_Base):
    access_token: str
    token_type: str = "bearer"


class AuthErrorCode(StrEnum):
    INVALID_CPF = "invalid_cpf"
    INVALID_REQUEST = "invalid_request"
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_DENIED = "account_denied"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    AUTH_UNAVAILABLE = "auth_unavailable"
    AUTH_INVALID_RESPONSE = "auth_invalid_response"
    LOGOUT_UNCONFIRMED = "logout_unconfirmed"


class AuthErrorResponse(_Base):
    code: AuthErrorCode
    message: str
    retry_after_seconds: int | None = None


class VocabularyLookupRequest(_StrictWireBase):
    # Normalized length is enforced after the bounded request body is read.
    text: StrictStr


class PronunciationRequest(_StrictWireBase):
    lookup_id: UUID


class VocabularyLookupResponse(_StrictWireBase):
    lookup_id: UUID
    source_text: CanonicalVocabularyText120
    translation: CanonicalVocabularyText120
    definition: CanonicalVocabularyDefinition


class VocabularyErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    NO_RESULT = "no_result"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"


class VocabularyErrorResponse(_StrictWireBase):
    code: VocabularyErrorCode
    message: StrictStr
    retry_after_seconds: Annotated[int, Field(ge=1, le=2_678_400)] | None = None


class AdminAttemptRow(_Base):
    attempt_id: UUID
    user_id: UUID
    email: CanonicalIdentityEmail
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
