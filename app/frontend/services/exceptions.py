"""Typed API failure surfaced to controllers and user-safe UI copy."""

from __future__ import annotations


class QuizApiError(Exception):
    """Preserve the stable API outcome without exposing raw upstream detail."""

    def __init__(
        self,
        status_code: int,
        detail: object,
        *,
        code: str | None = None,
        message: str | None = None,
        retry_after_seconds: int | None = None,
    ):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        self.message = message or (detail if isinstance(detail, str) else None)
        self.retry_after_seconds = retry_after_seconds
        super().__init__(self.message or code or f"Quiz API error ({status_code})")
