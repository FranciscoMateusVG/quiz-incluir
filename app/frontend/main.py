"""Entrypoint: configure the page and render the declarative app tree."""

from __future__ import annotations

import ipaddress

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
from widgets.auth_guard import protected_route_key


def canonicalize_client_ip(value: object) -> str | None:
    """Validate Flet's server-owned ingress IP before the loopback relay."""
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(str(value)))
    except ValueError:
        return None


def handle_auth_required(
    page: ft.Page,
    state: AppState,
    auth: AuthController,
    failed_token: str,
    failed_generation: int | None,
) -> None:
    """Apply one proven invalidation only to the request's owning session."""
    if (
        state.token != failed_token
        or state.auth_session_generation != failed_generation
    ):
        return
    auth.invalidate_validation()
    state.clear_session()
    state.remember_return_route(page.route)
    state.auth_notice = "Sua sessão expirou. Entre novamente."
    page.navigate("/")


def install_session_revalidation(
    page: ft.Page, state: AppState, auth: AuthController
) -> None:
    """Neutralize retained protected trees, then revalidate after reconnect."""

    def on_disconnect(e) -> None:
        # Every detached client loses ownership of work it started, including
        # a login that has not installed identity yet.
        state.supersede_async_work()
        if state.token is None or state.current_user is None:
            return
        # A disconnect ends the authority of every request started by the old
        # client attachment without treating reconnect as logout. Only the
        # forced /users/me check in on_connect can validate the retained token
        # for the new attachment.
        auth.invalidate_validation()
        # Flet 0.86.5 discards observable scheduling after detaching the
        # connection, while reconnect registration serializes the retained
        # server Page before on_connect. The explicit update performs the
        # component diff now (its network patch is intentionally dropped), so
        # the retained tree already contains only AuthGuard's neutral gate.
        page.update()

    async def on_connect(e) -> None:
        route = protected_route_key(page.route)
        if (
            route is not None
            and state.token is not None
            and state.current_user is not None
        ):
            await auth.revalidate(route, force=True)

    page.on_disconnect = on_disconnect
    page.on_connect = on_connect


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
    api = QuizApiClient(
        trusted_client_ip=canonicalize_client_ip(page.client_ip),
    )
    auth = AuthController(state, api)

    def on_auth_required(failed_token: str, failed_generation: int | None) -> None:
        # Only QuizApiClient's typed 401 auth_required path invokes this.
        # Outages and malformed upstream responses must preserve local state.
        handle_auth_required(page, state, auth, failed_token, failed_generation)

    api.set_auth_required_handler(
        on_auth_required, lambda: state.auth_session_generation
    )
    quiz_controller = QuizController(state, api)
    admin_controller = AdminController(state, api)

    install_session_revalidation(page, state, auth)
    page.render_views(make_app(state, auth, quiz_controller, admin_controller))


if __name__ == "__main__":
    ft.run(main, no_cdn=True)
