"""Admin: pick a quiz to inspect class-wide grades for."""

from __future__ import annotations

import flet as ft
from flet import component, use_effect, use_state

import theme
from controllers.admin_controller import AdminController
from state.app_state import AppState
from widgets.navbar import app_bar


@component
def AdminQuizListScreen(state: AppState, controller: AdminController):
    quizzes, set_quizzes = use_state([])
    error, set_error = use_state("")
    loading, set_loading = use_state(True)

    async def load():
        try:
            set_quizzes(await controller.list_quizzes())
            set_error("")
        except Exception as ex:
            set_error(f"Could not load quizzes: {ex}")
        finally:
            set_loading(False)

    use_effect(load, [])

    def _row(quiz):
        def on_click(e, q=quiz):
            ft.context.page.navigate(f"/admin/grades/{q.id}")

        return ft.Container(
            border_radius=theme.CARD_RADIUS,
            bgcolor=theme.SURFACE,
            border=ft.Border.all(1, theme.BORDER),
            content=ft.Container(
                padding=16,
                border_radius=theme.CARD_RADIUS,
                ink=True,
                on_click=on_click,
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(quiz.title, size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    f"{(quiz.category or '').replace('_', ' ').title()} · "
                                    f"{quiz.level} · {len(quiz.question_ids)} questions",
                                    size=13,
                                    color=theme.MUTED,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=theme.MUTED),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        )

    if loading:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [ft.ProgressRing(), ft.Text("Loading quizzes...", color=theme.MUTED)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    elif error:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.ERROR, size=50),
                    ft.Text(error, color=theme.ERROR, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    elif not quizzes:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.AUTO_STORIES_OUTLINED, size=72, color=theme.MUTED),
                    ft.Text("No quizzes available", size=22, weight=ft.FontWeight.BOLD),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )
    else:
        body = ft.Container(
            padding=20,
            expand=True,
            content=ft.Column(
                [
                    ft.Text("Class Grades", size=26, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Pick a quiz to see the grade distribution and per-question breakdown.",
                        color=theme.MUTED,
                    ),
                    ft.Column(
                        [_row(q) for q in quizzes],
                        spacing=12,
                    ),
                ],
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    return ft.View(
        route="/admin/grades",
        bgcolor=theme.BACKGROUND,
        appbar=app_bar(state, title="Class Grades"),
        controls=[
            theme.responsive(
                body,
                expand=True,
                col={"xs": 12, "sm": 12, "md": 11, "lg": 10, "xl": 9},
            )
        ],
    )
