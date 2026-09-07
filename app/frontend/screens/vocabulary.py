"""Authenticated Portuguese-to-English vocabulary and pronunciation page."""

from __future__ import annotations

import asyncio

import flet as ft
import theme
from controllers.auth_controller import AuthController
from controllers.vocabulary_controller import VocabularyController
from flet import component, use_effect, use_ref, use_state
from flet_audio import AudioState
from services.exceptions import QuizApiError
from services.media import (
    PLACEHOLDER_SRC,
    ensure_audio,
    play_audio_bytes,
    reset_audio_source,
)
from state.app_state import AppState
from widgets.navbar import app_bar


def vocabulary_error_message(error: Exception, fallback: str) -> str:
    """Return only the contract's user-safe message and bounded retry hint."""
    if not isinstance(error, QuizApiError) or not error.message:
        return fallback
    if error.retry_after_seconds is not None:
        return f"{error.message} Tente novamente em {error.retry_after_seconds}s."
    return error.message


def _audio_state_value(event: object) -> str:
    state = getattr(event, "state", "")
    return str(getattr(state, "value", state)).lower()


@component
def VocabularyScreen(
    state: AppState,
    controller: VocabularyController,
    auth: AuthController,
):
    """Render vocabulary tools without making provider calls on mount."""
    page = ft.context.page
    text, set_text = use_state("")
    result, set_result = use_state(None)
    lookup_status, set_lookup_status = use_state("idle")
    lookup_message, set_lookup_message = use_state("")
    audio_status, set_audio_status = use_state("idle")
    audio_message, set_audio_message = use_state("")

    lookup_owner = use_ref(0)
    lookup_busy = use_ref(False)
    audio_owner = use_ref(0)
    audio_bytes = use_ref(None)
    audio_busy = use_ref(False)

    def set_page_title() -> None:
        page.title = "Vocabulário | Incluir Quiz"

    use_effect(set_page_title, [])

    def on_audio_state(event) -> None:
        state_value = _audio_state_value(event)
        if state_value == AudioState.PLAYING.value:
            set_audio_status("playing")
            set_audio_message("Reproduzindo pronúncia…")
        elif state_value == AudioState.COMPLETED.value:
            audio_busy.current = False
            set_audio_status("completed")
            set_audio_message("Pronúncia concluída.")
        elif state_value == AudioState.DISPOSED.value:
            audio_busy.current = False
            set_audio_status("error")
            set_audio_message("Áudio indisponível neste navegador.")

    def bind_audio_events() -> None:
        audio = ensure_audio(page)
        audio.on_state_change = on_audio_state
        asyncio.create_task(reset_audio_source(page))

    def unbind_audio_events() -> None:
        lookup_owner.current += 1
        audio_owner.current += 1
        lookup_busy.current = False
        audio_busy.current = False
        audio = ensure_audio(page)
        audio.on_state_change = None
        if isinstance(audio.src, bytes):
            audio.src = PLACEHOLDER_SRC
        audio.update()

    use_effect(bind_audio_events, [], unbind_audio_events)

    async def translate(e) -> None:
        submitted = text.strip()
        if not submitted:
            set_lookup_status("error")
            set_lookup_message("Informe uma palavra ou frase em português.")
            return
        if lookup_busy.current:
            return

        try:
            session_token, session_generation = controller.session_snapshot()
        except RuntimeError:
            return
        lookup_busy.current = True
        lookup_owner.current += 1
        owner = lookup_owner.current
        audio_owner.current += 1
        audio_busy.current = False
        audio_bytes.current = None
        set_result(None)
        set_lookup_status("loading")
        set_lookup_message("Traduzindo…")
        set_audio_status("idle")
        set_audio_message("")
        await reset_audio_source(page)
        if not controller.session_is_current(session_token, session_generation):
            lookup_busy.current = False
            return

        try:
            next_result = await controller.lookup(submitted)
        except Exception as error:
            if owner != lookup_owner.current:
                return
            set_lookup_status("error")
            set_lookup_message(
                vocabulary_error_message(
                    error,
                    "Não foi possível buscar a tradução agora.",
                )
            )
            return
        finally:
            if owner == lookup_owner.current:
                lookup_busy.current = False

        if owner != lookup_owner.current or next_result is None:
            return
        set_result(next_result)
        set_lookup_status("success")
        set_lookup_message("Tradução pronta.")

    async def pronounce(e) -> None:
        active_result = (
            result
            if result is not None
            and state.vocabulary_lookup_id == str(result.lookup_id)
            else None
        )
        if active_result is None or audio_busy.current:
            return

        try:
            session_token, session_generation = controller.session_snapshot()
        except RuntimeError:
            return
        audio_busy.current = True
        audio_owner.current += 1
        owner = audio_owner.current
        set_audio_status("preparing")
        set_audio_message("Preparando pronúncia…")
        try:
            content = audio_bytes.current
            if content is None:
                content = await controller.pronunciation()
                if owner != audio_owner.current or content is None:
                    audio_busy.current = False
                    return
                audio_bytes.current = content
            if (
                owner != audio_owner.current
                or not controller.session_is_current(
                    session_token, session_generation
                )
            ):
                audio_busy.current = False
                return
            await play_audio_bytes(page, content)
            if (
                owner != audio_owner.current
                or not controller.session_is_current(
                    session_token, session_generation
                )
            ):
                audio_busy.current = False
                return
            set_audio_status("playing")
            set_audio_message("Reproduzindo pronúncia…")
        except Exception as error:
            if owner != audio_owner.current:
                return
            set_audio_status("error")
            set_audio_message(
                vocabulary_error_message(
                    error,
                    "Áudio indisponível neste navegador. Tente novamente.",
                )
            )
            audio_busy.current = False

    active_result = (
        result
        if result is not None and state.vocabulary_lookup_id == str(result.lookup_id)
        else None
    )

    if active_result is None:
        result_card: ft.Control = ft.Container(
            key="vocabulary-empty",
            padding=theme.SPACING_XL,
            border=ft.Border.all(1, theme.BORDER),
            border_radius=theme.CARD_RADIUS,
            bgcolor=theme.SURFACE,
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.TRANSLATE_ROUNDED,
                        color=theme.ACTION_PRIMARY,
                        size=28,
                    ),
                    ft.Text(
                        "Sua tradução aparecerá aqui.",
                        color=theme.TEXT_SECONDARY,
                        size=15,
                        expand=True,
                    ),
                ],
                spacing=theme.SPACING_2LG,
            ),
        )
    else:
        can_replay = audio_bytes.current is not None
        speaker_label = "Ouvir novamente" if can_replay else "Ouvir pronúncia"
        result_card = theme.card(
            ft.Column(
                [
                    ft.Text(
                        f"Português: {active_result.source_text}",
                        color=theme.TEXT_SECONDARY,
                        size=14,
                    ),
                    ft.Text(
                        "Tradução em inglês",
                        color=theme.TEXT_SECONDARY,
                        size=13,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        active_result.translation,
                        key="vocabulary-translation",
                        color=theme.TEXT_PRIMARY,
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        selectable=True,
                    ),
                    ft.Divider(height=1, color=theme.BORDER),
                    ft.Text(
                        "Definição em inglês",
                        color=theme.TEXT_SECONDARY,
                        size=13,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        active_result.definition,
                        key="vocabulary-definition",
                        color=theme.TEXT_PRIMARY,
                        size=17,
                        selectable=True,
                    ),
                    ft.Container(height=theme.SPACING_SM),
                    ft.OutlinedButton(
                        speaker_label,
                        key="vocabulary-pronunciation",
                        icon=ft.Icons.VOLUME_UP_ROUNDED,
                        height=theme.CONTROL_HEIGHT,
                        on_click=pronounce,
                        disabled=audio_status in {"preparing", "playing"},
                        style=ft.ButtonStyle(
                            color=theme.ACTION_PRIMARY,
                            side=ft.BorderSide(1, theme.ACTION_PRIMARY),
                            padding=ft.Padding.symmetric(vertical=12, horizontal=16),
                            shape=ft.RoundedRectangleBorder(radius=theme.INPUT_RADIUS),
                        ),
                    ),
                    ft.Semantics(
                        live_region=True,
                        label=audio_message or "Pronúncia pronta para iniciar.",
                        exclude_semantics=True,
                        content=ft.Text(
                            audio_message or "Pronúncia pronta para iniciar.",
                            key="vocabulary-audio-status",
                            color=(
                                theme.ERROR
                                if audio_status == "error"
                                else theme.TEXT_SECONDARY
                            ),
                            size=14,
                        ),
                    ),
                    ft.Text(
                        "Voz gerada por inteligência artificial.",
                        key="vocabulary-ai-disclosure",
                        color=theme.TEXT_SECONDARY,
                        size=12,
                    ),
                ],
                spacing=theme.SPACING_LG,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    lookup_status_text = lookup_message or (
        "Digite até 120 caracteres; palavras e frases são aceitas."
    )
    body = ft.Container(
        padding=ft.Padding.all(theme.SPACING_3LG),
        expand=True,
        content=ft.Column(
            [
                ft.Container(
                    padding=theme.SPACING_XL,
                    border_radius=theme.CARD_RADIUS,
                    bgcolor=theme.PRIMARY_LIGHT,
                    content=ft.Column(
                        [
                            ft.Text(
                                "Vocabulário",
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                "Traduza do português para o inglês e ouça a "
                                "pronúncia.",
                                size=16,
                                color=theme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=theme.SPACING_MD,
                    ),
                ),
                theme.text_field(
                    key="vocabulary-input",
                    label="Palavra ou frase em português",
                    value=text,
                    max_length=120,
                    on_change=lambda event: set_text(event.control.value or ""),
                    on_submit=translate,
                    autofocus=True,
                    multiline=False,
                    scroll_padding=ft.Padding.all(theme.SPACING_3XL),
                ),
                ft.Semantics(
                    live_region=True,
                    label=lookup_status_text,
                    exclude_semantics=True,
                    content=ft.Text(
                        lookup_status_text,
                        key="vocabulary-lookup-status",
                        color=(
                            theme.ERROR
                            if lookup_status == "error"
                            else theme.TEXT_SECONDARY
                        ),
                        size=14,
                    ),
                ),
                theme.primary_button(
                    "Traduzindo…" if lookup_status == "loading" else "Traduzir",
                    key="vocabulary-submit",
                    icon=(
                        None
                        if lookup_status == "loading"
                        else ft.Icons.TRANSLATE_ROUNDED
                    ),
                    on_click=translate,
                    disabled=lookup_status == "loading",
                    expand=True,
                ),
                result_card,
            ],
            spacing=theme.SPACING_2LG,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )

    return ft.View(
        route="/vocabulario",
        bgcolor=theme.BACKGROUND,
        appbar=app_bar(state, auth, title="Vocabulário"),
        controls=[
            theme.responsive(
                body,
                expand=True,
                col={"xs": 12, "sm": 11, "md": 9, "lg": 7, "xl": 6},
            )
        ],
    )
