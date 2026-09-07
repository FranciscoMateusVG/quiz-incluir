"""Shared top app bar with a named, role-safe account menu."""

from __future__ import annotations

import flet as ft
from quiz_shared.enums import UserRole

import theme
from config import APP_TITLE
from controllers.auth_controller import AuthController
from state.app_state import AppState


def app_bar(
    state: AppState, auth: AuthController, *, title: str = APP_TITLE
) -> ft.AppBar:
    page = ft.context.page
    logout_in_flight = False

    def go_quizzes(e):
        page.navigate("/quizzes")

    def go_vocabulary(e):
        page.navigate("/vocabulario")

    def go_admin(e):
        page.navigate("/admin/grades")

    async def logout(e):
        nonlocal logout_in_flight
        if logout_in_flight:
            return
        logout_in_flight = True
        try:
            await auth.logout()
            if auth.state.token is None:
                page.navigate("/")
        finally:
            logout_in_flight = False

    items: list[ft.PopupMenuItem] = [
        ft.PopupMenuItem(
            key="account-quizzes",
            content="Quizzes",
            icon=ft.Icons.QUIZ_OUTLINED,
            height=theme.CONTROL_HEIGHT,
            on_click=go_quizzes,
        ),
        ft.PopupMenuItem(
            key="account-vocabulary",
            content="Vocabulário",
            icon=ft.Icons.TRANSLATE_ROUNDED,
            height=theme.CONTROL_HEIGHT,
            on_click=go_vocabulary,
        ),
    ]

    if state.current_user is not None and state.current_user.role == UserRole.ADMIN:
        items.append(
            ft.PopupMenuItem(
                key="account-admin-grades",
                content="Notas",
                icon=ft.Icons.BAR_CHART_ROUNDED,
                height=theme.CONTROL_HEIGHT,
                on_click=go_admin,
            )
        )

    items.append(
        ft.PopupMenuItem(
            key="account-logout",
            content="Sair",
            icon=ft.Icons.LOGOUT,
            height=theme.CONTROL_HEIGHT,
            on_click=logout,
        )
    )

    account_menu = ft.PopupMenuButton(
        key="account-menu",
        tooltip="Conta",
        width=theme.CONTROL_HEIGHT,
        height=theme.CONTROL_HEIGHT,
        padding=6,
        menu_position=ft.PopupMenuPosition.UNDER,
        items=items,
        content=ft.Semantics(
            exclude_semantics=True,
            content=ft.CircleAvatar(
                radius=18,
                bgcolor=theme.ACTION_PRIMARY,
                content=ft.Text(
                    state.email[:1].upper() if state.email else "?",
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                ),
            ),
        ),
    )

    return ft.AppBar(
        bgcolor=theme.SURFACE,
        elevation=0,
        center_title=False,
        leading=ft.Container(
            padding=ft.Padding(left=16),
            alignment=ft.Alignment.CENTER,
            content=ft.Semantics(
                label="Programa Incluir",
                image=True,
                content=ft.Image(
                    src="logo.jpg",
                    height=38,
                    fit=ft.BoxFit.CONTAIN,
                    border_radius=10,
                ),
            ),
        ),
        leading_width=64,
        title=ft.Text(title, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
        actions=[ft.Container(padding=ft.Padding(right=12), content=account_menu)],
    )
