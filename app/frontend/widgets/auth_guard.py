"""Blocking route guard backed by the authoritative shared-auth session oracle."""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit

import flet as ft
from flet import component, use_effect
from quiz_shared.enums import UserRole

import theme
from controllers.auth_controller import AuthController
from state.app_state import AppState


def protected_route_key(route: str | None) -> str | None:
    """Return the local protected pathname, excluding query/fragment text."""
    path = urlsplit(route or "").path
    if path in {"/quizzes", "/results", "/admin/grades"}:
        return path
    if path.startswith("/quiz/") or path.startswith("/admin/grades/"):
        return path
    return None


def auth_checking_view(route: str) -> ft.View:
    return ft.View(
        route=route,
        controls=[
            ft.Container(
                key="auth-check-loading",
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Semantics(
                    container=True,
                    live_region=True,
                    label="Verificando acesso",
                    content=ft.Column(
                        tight=True,
                        spacing=theme.SPACING_LG,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.ProgressRing(),
                            ft.Text(
                                "Verificando acesso…",
                                color=theme.TEXT_SECONDARY,
                                size=16,
                            ),
                        ],
                    ),
                ),
            )
        ],
    )


@component
def _redirecting(to: str):
    def go():
        ft.context.page.navigate(to)

    use_effect(go, [])
    return auth_checking_view(ft.context.page.route or "/")


@component
def _AuthCheck(state: AppState, auth: AuthController, route: str):
    async def validate_on_mount():
        await auth.revalidate(route)

    use_effect(validate_on_mount, [route])

    if (
        state.auth_validation_status == "unavailable"
        and state.auth_validation_route == route
    ):

        async def retry(e):
            await auth.revalidate(route, force=True)

        message = (
            state.auth_validation_message
            or "Não foi possível verificar sua sessão. Tente novamente."
        )
        return ft.View(
            route=route,
            controls=[
                ft.Container(
                    key="auth-check-unavailable",
                    expand=True,
                    padding=theme.SPACING_XL,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Semantics(
                        container=True,
                        live_region=True,
                        label=message,
                        content=ft.Column(
                            tight=True,
                            spacing=theme.SPACING_2LG,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(
                                    ft.Icons.CLOUD_OFF_OUTLINED,
                                    color=theme.TEXT_SECONDARY,
                                    size=32,
                                ),
                                ft.Text(
                                    message,
                                    color=theme.TEXT_PRIMARY,
                                    size=16,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                theme.primary_button(
                                    ft.Text("Tentar novamente"),
                                    key="auth-check-retry",
                                    on_click=retry,
                                ),
                            ],
                        ),
                    ),
                )
            ],
        )

    return auth_checking_view(route)


@component
def AuthGuard(
    state: AppState,
    auth: AuthController,
    render: Callable[[], ft.Control],
    *,
    admin_only: bool = False,
) -> ft.Control:
    """Render no protected control until /users/me validates this route."""
    route = protected_route_key(ft.context.page.route)
    if route is None:
        return _redirecting("/")
    if state.token is None or state.current_user is None:
        state.remember_return_route(route)
        return _redirecting("/")
    if state.auth_validation_status != "valid" or state.auth_validation_route != route:
        return _AuthCheck(state, auth, route)
    if admin_only and state.current_user.role != UserRole.ADMIN:
        return _redirecting("/quizzes")
    return render()
