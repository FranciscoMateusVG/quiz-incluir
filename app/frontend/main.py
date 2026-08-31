"""Entrypoint: configure the page and render the declarative app tree."""

from __future__ import annotations

import flet as ft

import config
import theme
from controllers.admin_controller import AdminController
from controllers.auth_controller import AuthController
from controllers.quiz_controller import QuizController
from router import make_app
from services.api import QuizApiClient
from services.media import register_audio
from state.app_state import AppState


def main(page: ft.Page) -> None:
    page.title = config.APP_TITLE
    # Register the shared Audio service before the page is built so the web
    # client binds its invoke-method handler up front (registering late is what
    # produced "Timeout waiting for invoke method listener" on audio.play()).
    # FilePicker is deliberately NOT registered here: it's only needed much
    # later (the results-screen download button), and piling a second eager
    # service registration onto this same timing-sensitive startup path is a
    # needless risk to Audio's binding for no benefit — services/files.py
    # registers FilePicker lazily on its first actual use instead.
    register_audio(page)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = theme.page_theme()
    page.bgcolor = theme.BACKGROUND
    # Padding/max-width are handled per-screen via theme.responsive() so the
    # app is full-width on mobile and a centered column on desktop.
    page.padding = 0
    page.appbar = ft.AppBar(title=ft.Text(config.APP_TITLE), center_title=True)

    state = AppState()
    api = QuizApiClient(config.API_URL)
    auth = AuthController(state, api)
    quiz_controller = QuizController(state, api)
    admin_controller = AdminController(state, api)

    page.render_views(make_app(state, auth, quiz_controller, admin_controller))


if __name__ == "__main__":
    ft.run(main, no_cdn=True)

