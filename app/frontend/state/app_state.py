"""Reactive application state.

AppState is a dataclass decorated with flet's ``@observable`` so that any
attribute assignment notifies subscribed components, which re-render. Screens
receive the shared instance as a component argument; mutations (e.g.
``state.current_index += 1``) drive the UI automatically.
"""

from __future__ import annotations

import dataclasses

import flet as ft

from models.attempt import AttemptResult, User
from models.quiz import Quiz
from models.question import Question


@ft.observable
@dataclasses.dataclass
class AppState:
    token: str | None = None
    email: str = ""
    current_user: User | None = None

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