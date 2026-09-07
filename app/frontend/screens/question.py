from __future__ import annotations

import flet as ft
from flet import component, use_ref

import config
import theme
from config import APP_TITLE
from controllers.quiz_controller import QuizController
from state.app_state import AppState
from widgets.answers.answer_factory import AnswerWidget, answer_factory
from services.media import stop_audio
from widgets.feedback import notify
from widgets.media import media_area
from widgets.progress_indicator import build_progress
from widgets.question_card import question_card


@component
def QuestionScreen(state: AppState, controller: QuizController):
    answer_ref = use_ref(None)

    question = state.current_question
    if question is None:
        return ft.View(
            route="/quiz",
            bgcolor=theme.BACKGROUND,
            appbar=ft.AppBar(
                bgcolor=theme.SURFACE,
                elevation=0,
                title=ft.Text(APP_TITLE, color=theme.TEXT_PRIMARY),
                center_title=True,
            ),
            controls=[ft.Text("No question to display.", color=theme.TEXT_SECONDARY)],
        )

    idx = state.current_index
    total = state.total
    is_last = idx >= total - 1

    widget: AnswerWidget = answer_factory(question)
    widget.build(state.answers.get(str(question.id)))
    answer_ref.current = widget

    answered_indices = {
        i for i, q in enumerate(state.questions) if str(q.id) in state.answers
    }

    async def on_back(e):
        await stop_audio(ft.context.page)
        controller.previous()

    async def on_submit(e):
        await stop_audio(ft.context.page)
        response = widget.extract()
        if response is None:
            notify("Please answer the question first.", error=True)
            return
        try:
            await controller.submit(str(question.id), response)
        except Exception as ex:
            notify(f"Could not save your answer: {ex}", error=True)
            return
        if state.finished:
            ft.context.page.navigate("/results")

    back_btn = ft.OutlinedButton(
        "Back",
        key="question-back",
        icon=ft.Icons.ARROW_BACK,
        on_click=on_back,
        disabled=idx == 0,
        expand=True,
        height=theme.CONTROL_HEIGHT,
    )
    next_btn = ft.FilledButton(
        "Finish" if is_last else "Next",
        key="question-submit",
        icon=ft.Icons.CHECK if is_last else ft.Icons.ARROW_FORWARD,
        on_click=on_submit,
        expand=True,
        height=theme.CONTROL_HEIGHT,
    )

    quiz_media = state.quiz.media if state.quiz else []

    body = ft.Container(
        padding=20,
        expand=True,
        content=ft.Column(
            [
                build_progress(total, answered_indices, idx),
                ft.Container(height=12),
                # Shared context for the whole quiz (e.g. the reading passage or
                # listening audio) — a persistent header shown on every question,
                # not just the first, so it stays available for reference.
                *media_area(quiz_media, config.API_URL),
                question_card(question),
                ft.Container(height=8),
                widget.control,
                ft.Row([back_btn, next_btn], spacing=theme.SPACING_LG),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    return ft.View(
        route=f"/quiz/{idx}",
        bgcolor=theme.BACKGROUND,
        appbar=ft.AppBar(
            bgcolor=theme.SURFACE,
            elevation=0,
            title=ft.Text(
                f"Question {idx + 1} of {total}",
                weight=ft.FontWeight.BOLD,
                color=theme.TEXT_PRIMARY,
            ),
            center_title=True,
        ),
        controls=[
            theme.responsive(
                body,
                expand=True,
                col={"xs": 12, "sm": 12, "md": 10, "lg": 9, "xl": 8},
            )
        ],
    )
