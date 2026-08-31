from __future__ import annotations

import re

import flet as ft
from flet import component, use_state

import theme
from config import APP_TITLE
from controllers.auth_controller import AuthController

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@component
def LoginScreen(auth: AuthController):
    email, set_email = use_state("")
    password, set_password = use_state("")
    error, set_error = use_state("")
    loading, set_loading = use_state(False)

    async def on_login(e):
        value = (email or "").strip().lower()

        if not EMAIL_RE.match(value):
            set_error("Please enter a valid email address.")
            return

        set_loading(True)
        set_error("")

        try:
            await auth.login(value, password or "")
            ft.context.page.navigate("/quizzes")
        except Exception as ex:
            set_error(str(ex))
        finally:
            set_loading(False)

    form_card = theme.card(
        padding=40,
        radius=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=24,
            controls=[
                ft.Container(
                    width=80,
                    height=80,
                    border_radius=40,
                    bgcolor=theme.PRIMARY,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(
                        ft.Icons.SCHOOL,
                        color=ft.Colors.WHITE,
                        size=42,
                    ),
                ),
                ft.Column(
                    spacing=6,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            APP_TITLE,
                            size=32,
                            weight=ft.FontWeight.BOLD,
                            color=theme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "Practice smarter with interactive quizzes",
                            size=15,
                            color=theme.TEXT_SECONDARY,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                ),
                ft.TextField(
                    value=email,
                    on_change=lambda e: set_email(e.control.value),
                    label="Email",
                    prefix_icon=ft.Icons.EMAIL_OUTLINED,
                    keyboard_type=ft.KeyboardType.EMAIL,
                    autofocus=True,
                    border_radius=theme.INPUT_RADIUS,
                    border_color=theme.BORDER,
                    focused_border_color=theme.PRIMARY,
                ),
                ft.TextField(
                    value=password,
                    on_change=lambda e: set_password(e.control.value),
                    label="Password",
                    password=True,
                    can_reveal_password=True,
                    prefix_icon=ft.Icons.LOCK_OUTLINE,
                    border_radius=theme.INPUT_RADIUS,
                    border_color=theme.BORDER,
                    focused_border_color=theme.PRIMARY,
                    on_submit=on_login,
                ),
                ft.AnimatedSwitcher(
                    duration=200,
                    content=(
                        ft.Container(
                            padding=12,
                            bgcolor=theme.ERROR_LIGHT,
                            border_radius=12,
                            content=ft.Row(
                                spacing=10,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.ERROR_OUTLINE,
                                        color=theme.ERROR,
                                        size=18,
                                    ),
                                    ft.Text(
                                        error,
                                        color=theme.ERROR,
                                        expand=True,
                                    ),
                                ],
                            ),
                        )
                        if error
                        else ft.Container(height=0)
                    ),
                ),
                ft.Row(
                    [
                        ft.FilledButton(
                            expand=True,
                            disabled=loading,
                            on_click=on_login,
                            content=(
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=12,
                                    controls=[
                                        ft.ProgressRing(
                                            width=18,
                                            height=18,
                                            stroke_width=2,
                                            color=ft.Colors.WHITE,
                                        ),
                                        ft.Text("Signing in..."),
                                    ],
                                )
                                if loading
                                else ft.Text(
                                    "Continue",
                                    size=16,
                                    weight=ft.FontWeight.W_600,
                                )
                            ),
                        ),
                    ],
                ),
            ],
        ),
    )

    return ft.View(
        route="/",
        bgcolor=theme.BACKGROUND,
        controls=[
            ft.Container(
                expand=True,
                padding=24,
                alignment=ft.Alignment(0, 0),
                content=theme.responsive(
                    form_card, col={"xs": 12, "sm": 9, "md": 6, "lg": 4, "xl": 3}
                ),
            )
        ],
    )
