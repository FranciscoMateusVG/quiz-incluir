"""Typed HTTP client for the Quiz backend API.

Methods return pydantic models (parsed from the JSON responses) instead of
raw dicts, so the rest of the app never touches dictionaries. Fully async so
network calls don't block the Flet UI event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from models.admin import AdminAttemptRow, QuestionStatRow
from models.answer import AnswerRead
from models.attempt import Attempt, AttemptResult
from models.quiz import Quiz
from models.question import Question
from models.attempt import Token, User
from config import API_TIMEOUT, PRIVATE_API_ORIGIN
from services.exceptions import QuizApiError


class QuizApiClient:
    def __init__(
        self,
        timeout: float = API_TIMEOUT,
        trusted_client_ip: str | None = None,
    ):
        self.base_url = PRIVATE_API_ORIGIN
        self._client = httpx.AsyncClient(
            base_url=PRIVATE_API_ORIGIN,
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )
        self._operation_timeout = timeout
        self._trusted_client_ip = trusted_client_ip
        self._auth_required_handler: Callable[[str, int | None], None] | None = None
        self._auth_generation_getter: Callable[[], int] | None = None

    def set_auth_required_handler(
        self,
        handler: Callable[[str, int | None], None],
        generation_getter: Callable[[], int],
    ) -> None:
        """Install the per-page invalid-session transition after construction."""
        self._auth_required_handler = handler
        self._auth_generation_getter = generation_getter

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _headers(token: str | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _handle(self, resp: httpx.Response, *, token: str | None = None):
        if resp.status_code >= 400:
            detail: object = resp.text
            code = None
            message = None
            retry_after_seconds = None
            try:
                body = resp.json()
                if isinstance(body, dict):
                    # Phase A's canonical AuthError fields are top-level.
                    code = body.get("code")
                    message = body.get("message")
                    retry_after_seconds = body.get("retry_after_seconds")
                    detail = body.get("detail", message or detail)
            except Exception:
                pass
            error = QuizApiError(
                resp.status_code,
                detail,
                code=code if isinstance(code, str) else None,
                message=message if isinstance(message, str) else None,
                retry_after_seconds=(
                    retry_after_seconds
                    if isinstance(retry_after_seconds, int)
                    and not isinstance(retry_after_seconds, bool)
                    else None
                ),
            )
            if (
                resp.status_code == 401
                and error.code == "auth_required"
                and token is not None
                and self._auth_required_handler is not None
            ):
                self._auth_required_handler(
                    token, resp.extensions.get("quiz_auth_generation")
                )
            raise error
        if resp.status_code == 204:
            return None
        return resp.json()

    async def _request(
        self, method: str, path: str, *, auth_token: str | None = None, **kwargs
    ) -> httpx.Response:
        """Apply one absolute wall-clock budget to request plus body read."""
        auth_generation = (
            self._auth_generation_getter()
            if auth_token is not None and self._auth_generation_getter is not None
            else None
        )
        try:
            async with asyncio.timeout(self._operation_timeout):
                response = await self._client.request(
                    method, f"{self.base_url}{path}", **kwargs
                )
                await response.aread()
                response.extensions["quiz_auth_generation"] = auth_generation
                return response
        except TimeoutError as error:
            raise QuizApiError(
                503,
                "authentication service timed out",
                code="auth_unavailable",
                message="Não foi possível acessar o serviço agora.",
            ) from error

    # ---------- auth ----------

    async def login(self, cpf: str, password: str = "") -> Token:
        headers = None
        if self._trusted_client_ip is not None:
            # This dedicated attribution header is emitted only by the
            # same-process loopback relay. Never forward a browser XFF value.
            headers = {"X-Quiz-Client-IP": self._trusted_client_ip}
        resp = await self._request(
            "POST",
            "/api/v1/auth/token",
            data={"username": cpf, "password": password},
            headers=headers,
        )
        return Token.model_validate(self._handle(resp))

    async def logout(self, token: str) -> None:
        resp = await self._request(
            "POST",
            "/api/v1/auth/logout",
            auth_token=token,
            headers=self._headers(token),
        )
        if resp.status_code != 204:
            if resp.status_code >= 400:
                self._handle(resp, token=token)
            raise QuizApiError(
                resp.status_code,
                "logout response was not empty 204",
                code="auth_invalid_response",
                message="Não foi possível confirmar o encerramento da sessão.",
            )
        return None

    async def me(self, token: str) -> User:
        resp = await self._request(
            "GET",
            "/api/v1/users/me",
            auth_token=token,
            headers=self._headers(token),
        )
        return User.model_validate(self._handle(resp, token=token))

    # ---------- quizzes / questions ----------

    async def list_quizzes(self, token: str) -> list[Quiz]:
        resp = await self._request(
            "GET",
            "/api/v1/quizzes",
            auth_token=token,
            headers=self._headers(token),
        )
        return [Quiz.model_validate(item) for item in self._handle(resp, token=token)]

    async def get_question(self, token: str, question_id: str) -> Question:
        resp = await self._request(
            "GET",
            f"/api/v1/questions/{question_id}",
            auth_token=token,
            headers=self._headers(token),
        )
        return Question.model_validate(self._handle(resp, token=token))

    # ---------- attempts ----------

    async def start_attempt(self, token: str, quiz_id: str) -> Attempt:
        resp = await self._request(
            "POST",
            "/api/v1/attempts",
            auth_token=token,
            headers=self._headers(token),
            json={"quiz_id": str(quiz_id)},
        )
        return Attempt.model_validate(self._handle(resp, token=token))

    async def submit_answer(
        self, token: str, attempt_id: str, question_id: str, response: dict
    ) -> AnswerRead:
        resp = await self._request(
            "POST",
            f"/api/v1/attempts/{attempt_id}/answers",
            auth_token=token,
            headers=self._headers(token),
            json={"question_id": str(question_id), "response": response},
        )
        return AnswerRead.model_validate(self._handle(resp, token=token))

    async def finish_attempt(self, token: str, attempt_id: str) -> AttemptResult:
        resp = await self._request(
            "POST",
            f"/api/v1/attempts/{attempt_id}/finish",
            auth_token=token,
            headers=self._headers(token),
        )
        return AttemptResult.model_validate(self._handle(resp, token=token))

    async def download_report_pdf(self, token: str, attempt_id: str) -> bytes:
        resp = await self._request(
            "GET",
            f"/api/v1/attempts/{attempt_id}/report.pdf",
            auth_token=token,
            headers=self._headers(token),
        )
        if resp.status_code >= 400:
            self._handle(resp, token=token)
        return resp.content

    # ---------- admin ----------

    async def admin_list_attempts(
        self, token: str, quiz_id: str, level: str | None = None
    ) -> list[AdminAttemptRow]:
        params = {"level": level} if level else {}
        resp = await self._request(
            "GET",
            f"/api/v1/admin/quizzes/{quiz_id}/attempts",
            auth_token=token,
            headers=self._headers(token),
            params=params,
        )
        return [
            AdminAttemptRow.model_validate(item)
            for item in self._handle(resp, token=token)
        ]

    async def admin_question_stats(
        self, token: str, quiz_id: str, level: str | None = None
    ) -> list[QuestionStatRow]:
        params = {"level": level} if level else {}
        resp = await self._request(
            "GET",
            f"/api/v1/admin/quizzes/{quiz_id}/question-stats",
            auth_token=token,
            headers=self._headers(token),
            params=params,
        )
        return [
            QuestionStatRow.model_validate(item)
            for item in self._handle(resp, token=token)
        ]
