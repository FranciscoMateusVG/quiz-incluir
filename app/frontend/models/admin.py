"""Admin dashboard models: re-exports the shared read-schemas.

See ``quiz_shared.schemas`` for the field lists (``AdminAttemptRow``,
``QuestionStatRow``).
"""

from __future__ import annotations

from quiz_shared.schemas import AdminAttemptRow, QuestionStatRow

__all__ = ["AdminAttemptRow", "QuestionStatRow"]
