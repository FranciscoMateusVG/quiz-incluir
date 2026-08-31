"""Shared top app bar: brand logo, title, admin link (when applicable), avatar."""

from __future__ import annotations

import flet as ft
from quiz_shared.enums import UserRole

import theme
from config import APP_TITLE
from state.app_state import AppState


def app_bar(state: AppState, *, title: str = APP_TITLE) -> ft.AppBar:
    actions: list[ft.Control] = []

    if state.current_user is not None and state.current_user.role == UserRole.ADMIN:
        actions.append(
            ft.TextButton(
                "Admin: Grades",
                icon=ft.Icons.BAR_CHART_ROUNDED,
                on_click=lambda e: ft.context.page.navigate("/admin/grades"),
            )
        )

    actions.append(
        ft.Container(
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding(right=12),
            content=ft.CircleAvatar(
                radius=18,
                bgcolor=theme.PRIMARY,
                content=ft.Text(
                    state.email[:1].upper() if state.email else "?",
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                ),
            ),
        )
    )

    return ft.AppBar(
        bgcolor=theme.SURFACE,
        elevation=0,
        center_title=False,
        leading=ft.Container(
            padding=ft.Padding(left=16),
            alignment=ft.Alignment.CENTER,
            content=ft.Image(
                src="logo.jpg",
                height=38,
                fit=ft.BoxFit.CONTAIN,
                border_radius=10,
            ),
        ),
        leading_width=64,
        title=ft.Text(title, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
        actions=actions,
    )
