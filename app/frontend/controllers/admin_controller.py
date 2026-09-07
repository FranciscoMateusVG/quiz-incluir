"""Admin dashboard workflow: list quizzes, load class-wide grades and stats.

Read-only — this controller never mutates AppState, since the admin screens
own their own local (use_state) data rather than sharing state with the
student-facing quiz-taking flow.
"""

from __future__ import annotations

from models.admin import AdminAttemptRow, QuestionStatRow
from models.quiz import Quiz
from services.api import QuizApiClient
from state.app_state import AppState


class AdminController:
    def __init__(self, state: AppState, api: QuizApiClient):
        self.state = state
        self.api = api

    def _session_snapshot(self) -> tuple[str, int]:
        token = self.state.token
        if token is None:
            raise RuntimeError("Authentication is required.")
        return token, self.state.auth_session_generation

    def _session_is_current(self, token: str, generation: int) -> bool:
        return (
            self.state.token == token
            and self.state.auth_session_generation == generation
        )

    async def list_quizzes(self) -> list[Quiz] | None:
        token, generation = self._session_snapshot()
        try:
            quizzes = await self.api.list_quizzes(token)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        return quizzes if self._session_is_current(token, generation) else None

    async def list_attempts(
        self, quiz_id: str, level: str | None = None
    ) -> list[AdminAttemptRow] | None:
        token, generation = self._session_snapshot()
        try:
            attempts = await self.api.admin_list_attempts(token, quiz_id, level)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        return attempts if self._session_is_current(token, generation) else None

    async def get_question_stats(
        self, quiz_id: str, level: str | None = None
    ) -> list[QuestionStatRow] | None:
        token, generation = self._session_snapshot()
        try:
            stats = await self.api.admin_question_stats(token, quiz_id, level)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        return stats if self._session_is_current(token, generation) else None
