from __future__ import annotations

import flet as ft
from flet import component

import theme
from controllers.quiz_controller import QuizController
from services.files import save_bytes
from state.app_state import AppState
from widgets.feedback import notify


@component
def ResultsScreen(state: AppState, controller: QuizController):
    result = state.result
    score = (result.score or 0) if result else 0
    max_score = (result.max_score or 0) if result else 0
    pct = round(100 * score / max_score, 1) if max_score else 0.0
    passed = pct >= 50

    def again(e):
        ft.context.page.navigate("/quizzes")

    async def download_pdf(e):
        try:
            pdf_bytes = await controller.download_report()
            if pdf_bytes is None:
                return
            await save_bytes(f"quiz-report-{state.attempt_id}.pdf", pdf_bytes)
        except Exception as ex:
            notify(f"Could not download report: {ex}", error=True)

    body = theme.card(
        padding=32,
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.EMOJI_EVENTS if passed else ft.Icons.SENTIMENT_NEUTRAL,
                    size=64,
                    color=theme.PRIMARY if passed else theme.TEXT_SECONDARY,
                ),
                ft.Text(
                    "Quiz completed!",
                    size=26,
                    weight=ft.FontWeight.BOLD,
                    color=theme.TEXT_PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Text(
                    f"{score:g} / {max_score:g}",
                    size=44,
                    weight=ft.FontWeight.BOLD,
                    color=theme.PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"{pct}% correct",
                    size=16,
                    color=theme.MUTED_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                ft.Row(
                    [
                        ft.FilledButton(
                            "Take another quiz",
                            key="results-take-another",
                            on_click=again,
                            expand=True,
                            height=theme.CONTROL_HEIGHT,
                        ),
                        ft.OutlinedButton(
                            "Download PDF",
                            key="results-download",
                            icon=ft.Icons.PICTURE_AS_PDF,
                            on_click=download_pdf,
                            expand=True,
                            height=theme.CONTROL_HEIGHT,
                        ),
                    ],
                    spacing=theme.SPACING_LG,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    return ft.View(
        route="/results",
        bgcolor=theme.BACKGROUND,
        appbar=ft.AppBar(
            bgcolor=theme.SURFACE,
            elevation=0,
            title=ft.Text(
                "Results", weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY
            ),
            center_title=True,
        ),
        controls=[
            ft.Container(
                expand=True,
                padding=24,
                alignment=ft.Alignment(0, 0),
                content=theme.responsive(
                    body, col={"xs": 12, "sm": 9, "md": 6, "lg": 4, "xl": 3}
                ),
            )
        ],
    )
