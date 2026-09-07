"""Quiz workflow: load quizzes, run an attempt, finish it.

Controllers mutate :class:`AppState` and call the API; they never build UI.
Screens re-render automatically because they subscribe to the observable state.
"""

from __future__ import annotations

from models.attempt import AttemptResult
from models.quiz import Quiz
from services.api import QuizApiClient
from state.app_state import AppState


class QuizController:
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

    # ---------- loading ----------

    async def list_quizzes(self) -> list[Quiz] | None:
        token, generation = self._session_snapshot()
        try:
            quizzes = await self.api.list_quizzes(token)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        return quizzes if self._session_is_current(token, generation) else None

    async def start(self, quiz: Quiz) -> bool:
        token, generation = self._session_snapshot()
        questions = []
        for question_id in quiz.question_ids:
            try:
                question = await self.api.get_question(token, str(question_id))
            except Exception:
                if not self._session_is_current(token, generation):
                    return False
                raise
            if not self._session_is_current(token, generation):
                return False
            questions.append(question)
        try:
            attempt = await self.api.start_attempt(token, str(quiz.id))
        except Exception:
            if not self._session_is_current(token, generation):
                return False
            raise
        if not self._session_is_current(token, generation):
            return False
        if not questions:
            raise ValueError("This quiz has no questions.")
        self.state.quiz = quiz
        self.state.questions = questions
        self.state.answers = {}
        self.state.attempt_id = str(attempt.id)
        self.state.current_index = 0
        self.state.finished = False
        self.state.result = None
        return True

    # ---------- navigation within the attempt ----------

    @property
    def total(self) -> int:
        return self.state.total

    @property
    def current_index(self) -> int:
        return self.state.current_index

    @property
    def is_last(self) -> bool:
        return self.state.current_index >= self.state.total - 1

    def previous(self) -> None:
        if self.state.current_index > 0:
            self.state.current_index -= 1

    def next(self) -> None:
        if self.state.current_index < self.state.total - 1:
            self.state.current_index += 1

    # ---------- answering ----------

    async def submit(self, question_id: str, response: dict) -> bool:
        token, generation = self._session_snapshot()
        attempt_id = self.state.attempt_id
        try:
            await self.api.submit_answer(token, attempt_id, question_id, response)
        except Exception:
            if not self._session_is_current(token, generation):
                return False
            raise
        if not self._session_is_current(token, generation):
            return False
        self.state.answers = {**self.state.answers, question_id: response}
        if self.is_last:
            return await self._finish(token, generation, attempt_id) is not None
        else:
            self.state.current_index += 1
        return True

    async def _finish(
        self, token: str, generation: int, attempt_id: str | None
    ) -> AttemptResult | None:
        try:
            result = await self.api.finish_attempt(token, attempt_id)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        if not self._session_is_current(token, generation):
            return None
        self.state.result = result
        self.state.finished = True
        return result

    async def finish(self) -> AttemptResult | None:
        token, generation = self._session_snapshot()
        return await self._finish(token, generation, self.state.attempt_id)

    # ---------- report ----------

    async def download_report(self) -> bytes | None:
        token, generation = self._session_snapshot()
        try:
            report = await self.api.download_report_pdf(token, self.state.attempt_id)
        except Exception:
            if not self._session_is_current(token, generation):
                return None
            raise
        return report if self._session_is_current(token, generation) else None
