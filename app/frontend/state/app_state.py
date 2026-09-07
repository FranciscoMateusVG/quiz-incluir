"""Reactive application state.

AppState is a dataclass decorated with flet's ``@observable`` so that any
attribute assignment notifies subscribed components, which re-render. Screens
receive the shared instance as a component argument; mutations (e.g.
``state.current_index += 1``) drive the UI automatically.
"""

from __future__ import annotations

import dataclasses
import re
from uuid import UUID

import flet as ft

from models.attempt import AttemptResult, User
from models.quiz import Quiz
from models.question import Question

_ADMIN_GRADES_DETAIL_RE = re.compile(r"^/admin/grades/([^/?#]+)$")


def resolve_return_route(route: str | None, *, is_admin: bool) -> str:
    """Resolve one server-owned local destination through a typed allowlist."""
    if route == "/quizzes":
        return route
    if route == "/vocabulario":
        return route
    if route == "/admin/grades":
        return route if is_admin else "/quizzes"
    match = _ADMIN_GRADES_DETAIL_RE.fullmatch(route or "")
    if match:
        try:
            canonical_id = str(UUID(match.group(1)))
        except ValueError:
            return "/quizzes"
        return f"/admin/grades/{canonical_id}" if is_admin else "/quizzes"
    return "/quizzes"


@ft.observable
@dataclasses.dataclass
class AppState:
    token: str | None = None
    email: str = ""
    current_user: User | None = None
    return_route: str | None = None
    auth_notice: str = ""
    # A retained Flet session is only a resumption capability, never an
    # authorization decision. Protected routes remain neutral until /users/me
    # has validated the current token for the exact route being rendered.
    auth_validation_status: str = "unverified"
    auth_validation_route: str | None = None
    auth_validation_message: str = ""

    quiz: Quiz | None = None
    questions: list[Question] = dataclasses.field(default_factory=list)

    answers: dict[str, dict] = dataclasses.field(default_factory=dict)

    current_index: int = 0

    attempt_id: str | None = None
    finished: bool = False
    result: AttemptResult | None = None

    @property
    def current_question(self) -> Question | None:
        if not self.questions:
            return None
        return self.questions[self.current_index]

    @property
    def total(self) -> int:
        return len(self.questions)

    def remember_return_route(self, route: str | None) -> None:
        """Keep only local route text; validation and role checks occur on use."""
        self.return_route = route

    def consume_return_route(self, *, is_admin: bool) -> str:
        route = self.return_route
        self.return_route = None
        return resolve_return_route(route, is_admin=is_admin)

    def invalidate_auth_validation(self) -> None:
        """Require a fresh session oracle without discarding cached auth data."""
        self.auth_validation_status = "unverified"
        self.auth_validation_route = None
        self.auth_validation_message = ""

    def clear_session(self) -> None:
        """Clear auth and every attempt-bound value on logout or proven expiry."""
        self.token = None
        self.email = ""
        self.current_user = None
        self.return_route = None
        self.auth_notice = ""
        self.invalidate_auth_validation()
        self.quiz = None
        self.questions = []
        self.answers = {}
        self.current_index = 0
        self.attempt_id = None
        self.finished = False
        self.result = None
