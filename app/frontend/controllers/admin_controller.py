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

    async def list_quizzes(self) -> list[Quiz]:
        return await self.api.list_quizzes(self.state.token)

    async def list_attempts(
        self, quiz_id: str, level: str | None = None
    ) -> list[AdminAttemptRow]:
        return await self.api.admin_list_attempts(self.state.token, quiz_id, level)

    async def get_question_stats(
        self, quiz_id: str, level: str | None = None
    ) -> list[QuestionStatRow]:
        return await self.api.admin_question_stats(self.state.token, quiz_id, level)
