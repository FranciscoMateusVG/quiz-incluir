"""Route guard: redirects unauthenticated (or under-privileged) visitors away
from protected routes instead of rendering them.
"""

from __future__ import annotations

from typing import Callable

import flet as ft
from flet import component, use_effect
from quiz_shared.enums import UserRole

from state.app_state import AppState


@component
def _redirecting(to: str):
    def go():
        ft.context.page.navigate(to)

    use_effect(go, [])
    return ft.View(
        route=ft.context.page.route or "/",
        controls=[
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.ProgressRing(),
            )
        ],
    )


def require_auth(
    state: AppState, render: Callable[[], ft.Control], *, admin_only: bool = False
) -> ft.Control:
    """Render `render()` only if the session is authenticated (and, when
    `admin_only`, has the admin role) — otherwise redirect away.
    """
    if state.token is None or state.current_user is None:
        state.remember_return_route(ft.context.page.route)
        return _redirecting("/")
    if admin_only and state.current_user.role != UserRole.ADMIN:
        return _redirecting("/quizzes")
    return render()
