from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "shared"))
sys.path.insert(0, str(ROOT / "app" / "frontend"))

from controllers.auth_controller import AuthController  # noqa: E402
from controllers.admin_controller import AdminController  # noqa: E402
from controllers.quiz_controller import QuizController  # noqa: E402
import config as frontend_config  # noqa: E402
from main import (  # noqa: E402
    canonicalize_client_ip,
    handle_auth_required,
    install_session_revalidation,
)
import screens.login as login_screen  # noqa: E402
from screens.login import (  # noqa: E402
    format_cpf,
    login_error_message,
    normalize_cpf_digits,
)
from services.exceptions import QuizApiError  # noqa: E402
from services.api import QuizApiClient  # noqa: E402
import services.api as api_service  # noqa: E402
from state.app_state import AppState, resolve_return_route  # noqa: E402
from quiz_shared.enums import QuestionType, UserRole  # noqa: E402
from widgets.answers.answer_factory import answer_factory  # noqa: E402
from widgets.navbar import app_bar  # noqa: E402
import screens.picker as picker_screen  # noqa: E402
import screens.admin_grades as admin_grades_screen  # noqa: E402
import screens.admin_quiz_list as admin_quiz_list_screen  # noqa: E402
import screens.question as question_screen  # noqa: E402
import screens.results as results_screen  # noqa: E402
import theme  # noqa: E402
import widgets.auth_guard as auth_guard  # noqa: E402


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("203.0.113.42", "203.0.113.42"),
        ("2001:db8::42", "2001:db8::42"),
        ("2001:0db8:0000:0000:0000:0000:0000:0042", "2001:db8::42"),
    ],
)
def test_canonicalize_client_ip_accepts_only_valid_ip_literals(
    value: str, expected: str
) -> None:
    assert canonicalize_client_ip(value) == expected


@pytest.mark.parametrize(
    "value",
    [None, "", "not-an-ip", "203.0.113.42, 198.51.100.2", "203.0.113.999"],
)
def test_canonicalize_client_ip_rejects_missing_or_invalid_values(
    value: str | None,
) -> None:
    assert canonicalize_client_ip(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        ("0", "0"),
        ("0914", "091.4"),
        ("0914999", "091.499.9"),
        ("0914999168", "091.499.916-8"),
        ("09149991680", "091.499.916-80"),
        ("091.499.916-80", "091.499.916-80"),
    ],
)
def test_format_cpf_supports_incremental_masking(value: str, expected: str) -> None:
    assert format_cpf(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "09149991680",
        "091.499.916-80",
        "  09149991680  ",
        "\t091.499.916-80\n",
    ],
)
def test_normalize_cpf_accepts_only_the_two_contract_shapes(value: str) -> None:
    assert normalize_cpf_digits(value) == "09149991680"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0914999168",
        "091499916800",
        "091 499 916 80",
        "091.499.91680",
        "091-499-916.80",
        "091a49991680",
        "+5509149991680",
        "٠٩١٤٩٩٩١٦٨٠",
    ],
)
def test_normalize_cpf_rejects_partial_or_loosely_stripped_input(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_cpf_digits(value)


@pytest.mark.parametrize(
    ("route", "is_admin", "expected"),
    [
        (None, False, "/quizzes"),
        ("", False, "/quizzes"),
        ("/quizzes", False, "/quizzes"),
        ("/vocabulario", False, "/vocabulario"),
        ("/admin/grades", False, "/quizzes"),
        ("/admin/grades", True, "/admin/grades"),
        (
            "/admin/grades/123e4567-e89b-12d3-a456-426614174000",
            True,
            "/admin/grades/123e4567-e89b-12d3-a456-426614174000",
        ),
        (
            "/admin/grades/123e4567-e89b-12d3-a456-426614174000",
            False,
            "/quizzes",
        ),
    ],
)
def test_resolve_return_route_keeps_only_role_authorized_local_destinations(
    route: str | None, is_admin: bool, expected: str
) -> None:
    assert resolve_return_route(route, is_admin=is_admin) == expected


@pytest.mark.parametrize(
    "route",
    [
        "https://evil.example/quizzes",
        "//evil.example/quizzes",
        "/quizzes?next=https://evil.example",
        "/quizzes#fragment",
        "/quiz/0",
        "/admin/grades/not-a-uuid",
        "/admin/grades/123e4567-e89b-12d3-a456-426614174000/extra",
        "/%2f%2fevil.example",
    ],
)
def test_resolve_return_route_rejects_non_allowlisted_destinations(route: str) -> None:
    assert resolve_return_route(route, is_admin=True) == "/quizzes"


def test_return_route_is_consumed_once_and_role_checked_at_consumption() -> None:
    state = AppState()
    state.remember_return_route("/admin/grades")

    assert state.consume_return_route(is_admin=False) == "/quizzes"
    assert state.return_route is None
    assert state.consume_return_route(is_admin=True) == "/quizzes"


def test_ip_attribution_is_not_a_login_ui_or_controller_input() -> None:
    assert tuple(inspect.signature(login_screen.LoginScreen).parameters) == ("auth",)
    assert tuple(inspect.signature(AuthController.login).parameters) == (
        "self",
        "cpf",
        "password",
    )
    assert tuple(inspect.signature(QuizApiClient.login).parameters) == (
        "self",
        "cpf",
        "password",
    )


def test_quiz_api_client_pins_private_loopback_and_ignores_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_kwargs: dict[str, object] = {}

    class ClientProbe:
        def __init__(self, **kwargs: object) -> None:
            constructor_kwargs.update(kwargs)

    monkeypatch.setattr(api_service.httpx, "AsyncClient", ClientProbe)
    monkeypatch.setattr(
        frontend_config, "API_URL", "https://attacker-controlled.example.test"
    )

    api = QuizApiClient(timeout=3.25)

    assert tuple(inspect.signature(QuizApiClient).parameters) == (
        "timeout",
        "trusted_client_ip",
    )
    assert frontend_config.PRIVATE_API_ORIGIN == "http://127.0.0.1:8000"
    assert api.base_url == "http://127.0.0.1:8000"
    assert constructor_kwargs == {
        "base_url": "http://127.0.0.1:8000",
        "timeout": 3.25,
        "trust_env": False,
        "follow_redirects": False,
    }


def test_login_threads_one_trusted_client_ip_header_and_other_calls_do_not() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/auth/token"):
            return httpx.Response(
                200,
                json={"access_token": "opaque-cookie", "token_type": "bearer"},
            )
        return httpx.Response(200, json=[])

    async def exercise() -> None:
        api = QuizApiClient(
            trusted_client_ip="2001:db8::42",
        )
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await api.login("09149991680", "password")
            await api.list_quizzes("opaque-cookie")
        finally:
            await api.aclose()

    asyncio.run(exercise())

    assert len(requests) == 2
    login_headers = requests[0].headers.multi_items()
    list_headers = requests[1].headers.multi_items()
    assert [value for name, value in login_headers if name == "x-quiz-client-ip"] == [
        "2001:db8::42"
    ]
    assert not any(name == "x-forwarded-for" for name, _ in login_headers)
    assert not any(name == "x-quiz-client-ip" for name, _ in list_headers)
    assert not any(name == "x-forwarded-for" for name, _ in list_headers)


def test_login_omits_client_ip_headers_when_runtime_has_no_trusted_value() -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"access_token": "opaque-cookie", "token_type": "bearer"},
        )

    async def exercise() -> None:
        api = QuizApiClient(
            trusted_client_ip=None,
        )
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await api.login("09149991680", "password")
        finally:
            await api.aclose()

    asyncio.run(exercise())

    headers = captured[0].headers.multi_items()
    assert not any(name == "x-quiz-client-ip" for name, _ in headers)
    assert not any(name == "x-forwarded-for" for name, _ in headers)


def test_login_errors_are_classified_without_exposing_backend_detail() -> None:
    cases = {
        "invalid_cpf": QuizApiError(422, "invalid_cpf"),
        "invalid_credentials": QuizApiError(401, "invalid_credentials"),
        "account_denied": QuizApiError(403, "account_denied"),
        "rate_limited": QuizApiError(429, "rate_limited"),
        "auth_unavailable": QuizApiError(503, "auth_unavailable"),
        "auth_invalid_response": QuizApiError(502, "auth_invalid_response"),
    }

    messages = {code: login_error_message(error) for code, error in cases.items()}

    assert len(set(messages.values())) == len(messages)
    assert messages["invalid_credentials"] == "CPF ou senha inválidos."
    assert messages["auth_unavailable"] == (
        "Não foi possível entrar agora. Tente novamente."
    )
    for code, message in messages.items():
        assert code not in message


def test_login_error_mapping_does_not_claim_legacy_nested_error_contract() -> None:
    error = QuizApiError(403, {"code": "account_denied"})

    assert login_error_message(error) == "Não foi possível entrar. Tente novamente."


def test_typed_error_payload_keeps_code_and_retry_metadata() -> None:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://quiz.example.test/api/v1/auth/token"),
        json={
            "code": "rate_limited",
            "message": "Too many attempts",
            "retry_after_seconds": 37,
        },
    )
    api = QuizApiClient()

    with pytest.raises(QuizApiError) as raised:
        api._handle(response)

    asyncio.run(api.aclose())
    assert raised.value.status_code == 429
    assert raised.value.code == "rate_limited"
    assert raised.value.retry_after_seconds == 37
    assert login_error_message(raised.value) == (
        "Muitas tentativas. Tente novamente em 37 segundos."
    )


@pytest.mark.parametrize(
    ("status_code", "code", "expected_invalidations"),
    [
        (401, "auth_required", 1),
        (401, "invalid_credentials", 0),
        (502, "auth_invalid_response", 0),
        (503, "auth_unavailable", 0),
    ],
)
def test_only_typed_auth_required_401_invalidates_local_session(
    status_code: int, code: str, expected_invalidations: int
) -> None:
    invalidations: list[str] = []
    api = QuizApiClient()
    api.set_auth_required_handler(
        lambda token, generation: invalidations.append(
            f"invalidated:{token}:{generation}"
        ),
        lambda: 0,
    )
    response = httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://quiz.example.test/api/v1/quizzes"),
        json={"code": code, "message": "safe backend message"},
    )

    with pytest.raises(QuizApiError):
        api._handle(response, token="request-token")

    asyncio.run(api.aclose())
    assert len(invalidations) == expected_invalidations


def test_unknown_login_error_uses_safe_copy() -> None:
    secret_detail = "upstream diagnostic containing sensitive implementation detail"

    message = login_error_message(RuntimeError(secret_detail))

    assert message == "Não foi possível entrar. Tente novamente."
    assert secret_detail not in message


@pytest.mark.parametrize("status_code", [200, 401, 502, 503])
def test_api_logout_requires_204_for_confirmation(status_code: int) -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code,
            json={"detail": {"code": "auth_unavailable"}},
        )

    async def exercise() -> QuizApiError:
        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(QuizApiError) as raised:
                await api.logout("opaque-cookie")
            return raised.value
        finally:
            await api.aclose()

    error = asyncio.run(exercise())

    assert error.status_code == status_code
    assert len(captured) == 1
    assert captured[0].url.path == "/api/v1/auth/logout"
    assert captured[0].headers["authorization"] == "Bearer opaque-cookie"
    assert "x-quiz-client-ip" not in captured[0].headers
    assert "x-forwarded-for" not in captured[0].headers


def test_api_logout_treats_204_as_confirmed() -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    async def exercise() -> None:
        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            result = await api.logout("opaque-cookie")
            assert result is None
        finally:
            await api.aclose()

    asyncio.run(exercise())

    assert len(captured) == 1
    assert captured[0].url.path == "/api/v1/auth/logout"


class _LogoutApi:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.tokens: list[str] = []

    async def logout(self, token: str) -> None:
        self.tokens.append(token)
        if self.error is not None:
            raise self.error


def _authenticated_state() -> AppState:
    state = AppState()
    state.token = "opaque-better-auth-cookie"
    state.email = "learner@example.test"
    state.current_user = object()  # type: ignore[assignment]
    state.quiz = object()  # type: ignore[assignment]
    state.questions = [object()]  # type: ignore[list-item]
    state.answers = {"question": {"selected": "answer"}}
    state.current_index = 3
    state.attempt_id = "attempt-id"
    state.finished = True
    state.result = object()  # type: ignore[assignment]
    return state


def _assert_local_session_cleared(state: AppState) -> None:
    assert state.token is None
    assert state.email == ""
    assert state.current_user is None
    assert state.quiz is None
    assert state.questions == []
    assert state.answers == {}
    assert state.current_index == 0
    assert state.attempt_id is None
    assert state.finished is False
    assert state.result is None


def test_logout_confirms_upstream_and_clears_all_local_session_state() -> None:
    state = _authenticated_state()
    api = _LogoutApi()
    auth = AuthController(state, api)  # type: ignore[arg-type]

    confirmed = asyncio.run(auth.logout())

    assert confirmed is True
    assert api.tokens == ["opaque-better-auth-cookie"]
    assert state.auth_notice == ""
    _assert_local_session_cleared(state)


def test_logout_failure_still_clears_local_state_and_reports_unconfirmed() -> None:
    state = _authenticated_state()
    api = _LogoutApi(error=QuizApiError(503, "auth_unavailable"))
    auth = AuthController(state, api)  # type: ignore[arg-type]

    confirmed = asyncio.run(auth.logout())

    assert confirmed is False
    assert api.tokens == ["opaque-better-auth-cookie"]
    assert state.auth_notice == (
        "Você saiu do Quiz, mas não foi possível confirmar o encerramento "
        "da sessão no servidor."
    )
    _assert_local_session_cleared(state)


def _walk_controls(control: Any):
    """Traverse a constructed Flet control tree without pretending to render it."""
    seen: set[int] = set()
    pending = [control]
    child_attributes = (
        "content",
        "controls",
        "actions",
        "items",
        "leading",
        "suffix",
        "suffix_icon",
        "title",
    )
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attribute in child_attributes:
            child = getattr(current, attribute, None)
            if isinstance(child, (list, tuple)):
                pending.extend(child)
            elif child is not None and not isinstance(child, (str, int, float, bool)):
                pending.append(child)


def _keyed(control: Any, key: str) -> Any:
    return next(item for item in _walk_controls(control) if item.key == key)


def _text_values(control: Any) -> set[str]:
    return {
        item.value
        for item in _walk_controls(control)
        if isinstance(item, login_screen.ft.Text) and isinstance(item.value, str)
    }


def test_login_component_tree_has_named_minimum_size_auth_controls(monkeypatch) -> None:
    state = AppState()
    state.auth_notice = "Sua sessão expirou. Entre novamente."
    auth = SimpleNamespace(state=state)
    page = SimpleNamespace(
        title="",
        route="/",
        update=lambda: None,
        navigate=lambda route: None,
    )
    monkeypatch.setattr(
        login_screen, "use_state", lambda value: (value, lambda _: None)
    )
    monkeypatch.setattr(
        login_screen, "use_ref", lambda value: SimpleNamespace(current=value)
    )
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(auth)

    cpf = _keyed(view, "login-cpf")
    password = _keyed(view, "login-password")
    password_visibility = _keyed(view, "login-password-visibility")
    password_semantics = _keyed(view, "login-password-visibility-semantics")
    submit = _keyed(view, "login-submit")
    status = _keyed(view, "login-status")
    semantics = [
        item
        for item in _walk_controls(view)
        if isinstance(item, login_screen.ft.Semantics)
    ]

    assert cpf.label == "CPF"
    assert cpf.keyboard_type == login_screen.ft.KeyboardType.NUMBER
    assert cpf.autofocus is True
    assert cpf.autocorrect is False
    assert cpf.enable_suggestions is False
    assert cpf.size_constraints.min_height >= 44
    assert password.label == "Senha"
    assert password.password is True
    assert password.autocorrect is False
    assert password.enable_suggestions is False
    assert callable(password.on_change)
    assert callable(password.on_submit)
    assert password.size_constraints.min_height >= 44
    assert password_visibility.tooltip == "Mostrar senha"
    assert password_visibility.width >= 44
    assert password_visibility.height >= 44
    assert password_semantics.label == "Mostrar senha"
    assert password_semantics.button is True
    assert password_semantics.focusable is True
    assert password_semantics.exclude_semantics is True
    assert callable(password_semantics.on_tap)
    assert submit.height >= 44
    assert "Entrar no Quiz" in _text_values(submit)
    assert any(item.live_region and item.content is status for item in semantics)


def test_login_cpf_change_handles_typing_mid_edit_and_end_delete(monkeypatch) -> None:
    cpf_updates: list[str] = []
    hook_values = iter(
        [
            ("", cpf_updates.append),
            ("", lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=lambda route: None
    )
    monkeypatch.setattr(login_screen, "use_state", lambda initial: next(hook_values))
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(SimpleNamespace(state=AppState()))
    cpf = _keyed(view, "login-cpf")
    browser_values = [
        "1",
        "10",
        "103",
        "1032",
        "103239",
        "1032396",
        "10323969623",
        "103.23.696-23",
        "103.239.696-23",
        "103.239.696-2",
        "103.239.696-23",
    ]
    for value in browser_values:
        cpf.on_change(SimpleNamespace(control=SimpleNamespace(value=value)))

    assert cpf_updates == [
        "1",
        "10",
        "103",
        "103.2",
        "103.239",
        "103.239.6",
        "103.239.696-23",
        "103.23.696-23",
        "103.239.696-23",
        "103.239.696-2",
        "103.239.696-23",
    ]


@pytest.mark.parametrize(
    ("pasted", "expected"),
    [
        ("10323969623", "103.239.696-23"),
        ("103.239.696-23", "103.239.696-23"),
    ],
)
def test_login_cpf_change_accepts_supported_whole_value_paste_shapes(
    pasted: str,
    expected: str,
    monkeypatch,
) -> None:
    cpf_updates: list[str] = []
    hook_values = iter(
        [
            ("", cpf_updates.append),
            ("", lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=lambda route: None
    )
    monkeypatch.setattr(login_screen, "use_state", lambda initial: next(hook_values))
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(SimpleNamespace(state=AppState()))
    _keyed(view, "login-cpf").on_change(
        SimpleNamespace(control=SimpleNamespace(value=pasted))
    )

    assert cpf_updates == [expected]


def test_login_password_change_preserves_complete_edit_buffers(monkeypatch) -> None:
    password_updates: list[str] = []
    hook_values = iter(
        [
            ("", lambda value: None),
            ("", password_updates.append),
            (False, lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=lambda route: None
    )
    monkeypatch.setattr(login_screen, "use_state", lambda initial: next(hook_values))
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(SimpleNamespace(state=AppState()))
    password = _keyed(view, "login-password")
    browser_values = ["p", "pa", "pas", "pass", "pas", "pass"]
    for value in browser_values:
        password.on_change(SimpleNamespace(control=SimpleNamespace(value=value)))

    assert password_updates == browser_values


def test_login_password_latest_rendered_buffer_reaches_submit(monkeypatch) -> None:
    final_buffer = "input-buffer"
    state = AppState(return_route="/quizzes")
    received: list[tuple[str, str]] = []

    class FakeAuth:
        def __init__(self) -> None:
            self.state = state

        async def login(self, cpf: str, password: str) -> bool:
            received.append((cpf, password))
            self.state.current_user = SimpleNamespace(role=UserRole.STUDENT)
            return True

        def mark_validated_route(self, route: str) -> None:
            pass

    hook_values = iter(
        [
            ("103.239.696-23", lambda value: None),
            (final_buffer, lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    routes: list[str] = []
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=routes.append
    )
    monkeypatch.setattr(login_screen, "use_state", lambda initial: next(hook_values))
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(FakeAuth())
    asyncio.run(_keyed(view, "login-submit").on_click(None))

    assert received == [("10323969623", final_buffer)]
    assert routes == ["/quizzes"]


@pytest.mark.parametrize(
    ("role", "has_admin_item"),
    [(UserRole.STUDENT, False), (UserRole.ADMIN, True)],
)
def test_account_menu_is_named_and_preserves_quiz_local_role_visibility(
    role: UserRole, has_admin_item: bool, monkeypatch
) -> None:
    state = AppState()
    state.email = "learner@example.test"
    state.current_user = SimpleNamespace(role=role)  # type: ignore[assignment]
    auth = SimpleNamespace(logout=lambda: None)
    page = SimpleNamespace(navigate=lambda route: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    bar = app_bar(state, auth)  # type: ignore[arg-type]

    account = _keyed(bar, "account-menu")
    quizzes = _keyed(bar, "account-quizzes")
    logout = _keyed(bar, "account-logout")
    keyed = {item.key for item in _walk_controls(bar)}
    semantics = [
        item
        for item in _walk_controls(bar)
        if isinstance(item, login_screen.ft.Semantics)
    ]

    assert account.tooltip == "Conta"
    assert account.width >= 44
    assert account.height >= 44
    assert quizzes.height == 48
    assert logout.height == 48
    assert quizzes.content == "Quizzes"
    assert logout.content == "Sair"
    assert ("account-admin-grades" in keyed) is has_admin_item
    if has_admin_item:
        assert _keyed(bar, "account-admin-grades").content == "Notas"
    assert not any(item.label == "Conta" for item in semantics)


def test_answer_choice_tree_has_stable_keys_and_merged_accessible_names() -> None:
    """Tree-only contract: runtime hit geometry remains an E2E responsibility."""
    question = SimpleNamespace(
        type=QuestionType.MULTIPLE_CHOICE,
        options=["First answer", "A second answer that can wrap"],
    )

    control = answer_factory(question).build(None)

    first = _keyed(control, "answer-choice-0")
    second = _keyed(control, "answer-choice-1")
    names = {
        item.label
        for item in _walk_controls(control)
        if isinstance(item, login_screen.ft.Semantics) and item.container
    }
    assert first.value == "First answer"
    assert second.value == "A second answer that can wrap"
    assert first.height >= 44
    assert second.height >= 44
    assert names == {"First answer", "A second answer that can wrap"}


def test_answer_multiselect_tree_has_stable_keys_and_accessible_names() -> None:
    """Tree-only contract; native checkbox geometry is verified in-browser."""
    question = SimpleNamespace(
        type=QuestionType.MULTIPLE_SELECTION,
        options=["Option one", "Option two"],
    )

    control = answer_factory(question).build(None)

    first = _keyed(control, "answer-multiselect-0")
    second = _keyed(control, "answer-multiselect-1")
    names = {
        item.label
        for item in _walk_controls(control)
        if isinstance(item, login_screen.ft.Semantics) and item.container
    }
    assert first.semantics_label == "Option one"
    assert second.semantics_label == "Option two"
    assert names == {"Option one", "Option two"}


def test_answer_true_false_tree_has_stable_named_controls() -> None:
    """Tree-only contract; Flet's native radio target is not measured here."""
    question = SimpleNamespace(
        type=QuestionType.TRUE_FALSE,
        options=[],
    )

    control = answer_factory(question).build(None)

    true_control = _keyed(control, "answer-true")
    false_control = _keyed(control, "answer-false")
    assert true_control.label == "True"
    assert false_control.label == "False"
    assert true_control.height >= 44
    assert false_control.height >= 44


def test_answer_short_text_tree_has_stable_label_and_minimum_height() -> None:
    """Tree-only size guard; settled rendered geometry remains an E2E gate."""
    question = SimpleNamespace(
        type=QuestionType.SHORT_TEXT,
        options=[],
    )

    control = answer_factory(question).build(None)

    field = _keyed(control, "answer-text")
    assert field.label == "Your answer"
    assert field.size_constraints.min_height >= 44


def test_question_action_tree_has_stable_keys_names_and_minimum_heights(
    monkeypatch,
) -> None:
    """Pure component-build assertion; it does not claim runtime actionability."""
    question = SimpleNamespace(
        id="question-1",
        type=QuestionType.TRUE_FALSE,
        options=[],
        prompt="Is this sentence correct?",
        media=[],
    )
    state = AppState()
    state.questions = [question]  # type: ignore[list-item]
    state.current_index = 0
    controller = SimpleNamespace()
    monkeypatch.setattr(
        question_screen,
        "use_ref",
        lambda initial: SimpleNamespace(current=initial),
    )

    view = question_screen.QuestionScreen.__wrapped__(state, controller)

    back = _keyed(view, "question-back")
    submit = _keyed(view, "question-submit")
    assert back.content == "Back"
    assert back.height >= 44
    assert submit.content == "Finish"
    assert submit.height >= 44


def test_results_action_tree_has_stable_keys_names_and_minimum_heights() -> None:
    """Pure component-build assertion; download/navigation stay runtime gates."""
    state = AppState()
    state.result = SimpleNamespace(score=3, max_score=4)  # type: ignore[assignment]
    controller = SimpleNamespace()

    view = results_screen.ResultsScreen.__wrapped__(state, controller)

    take_another = _keyed(view, "results-take-another")
    download = _keyed(view, "results-download")
    assert take_another.content == "Take another quiz"
    assert take_another.height >= 44
    assert download.content == "Download PDF"
    assert download.height >= 44


def test_picker_quiz_card_tree_exposes_named_button_semantics(monkeypatch) -> None:
    """Tree-only semantics check; click reachability still requires a browser."""
    quiz = SimpleNamespace(
        id="quiz-1",
        title="Intermediate Check",
        description="A deterministic seeded quiz",
        level="B1",
        category="reading",
        question_ids=["question-1"],
    )
    state = AppState()
    state.email = "learner@example.test"
    state.current_user = SimpleNamespace(role=UserRole.STUDENT)  # type: ignore[assignment]
    auth = SimpleNamespace(logout=lambda: None)
    starts: list[object] = []

    class Controller:
        async def start(self, selected) -> bool:
            starts.append(selected)
            return True

    controller = Controller()
    routes: list[str] = []
    page = SimpleNamespace(navigate=routes.append)
    hook_states = iter(
        [
            ([quiz], lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
        ]
    )
    monkeypatch.setattr(picker_screen, "use_state", lambda initial: next(hook_states))
    monkeypatch.setattr(picker_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = picker_screen.QuizPickerScreen.__wrapped__(state, controller, auth)

    action = _keyed(view, "quiz-card-quiz-1")
    search = _keyed(view, "quiz-search")
    assert isinstance(action, login_screen.ft.Button)
    assert action.tooltip == "Abrir quiz Intermediate Check"
    assert callable(action.on_click)
    assert search.label == "Search quizzes"
    asyncio.run(action.on_click(None))
    assert starts == [quiz]
    assert routes == ["/quiz/0"]


def test_picker_does_not_navigate_when_stale_start_returns_false(monkeypatch) -> None:
    quiz = SimpleNamespace(
        id="quiz-1",
        title="Intermediate Check",
        description="A deterministic seeded quiz",
        level="B1",
        category="reading",
        question_ids=["question-1"],
    )

    class Controller:
        async def start(self, selected) -> bool:
            return False

    hooks = iter(
        [
            ([quiz], lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
        ]
    )
    routes: list[str] = []
    monkeypatch.setattr(picker_screen, "use_state", lambda initial: next(hooks))
    monkeypatch.setattr(picker_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(
        picker_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=routes.append)),
    )

    view = picker_screen.QuizPickerScreen.__wrapped__(
        AppState(), Controller(), SimpleNamespace()
    )
    asyncio.run(_keyed(view, "quiz-card-quiz-1").on_click(None))
    assert routes == []


def test_question_does_not_navigate_when_stale_submit_returns_false(
    monkeypatch,
) -> None:
    question = SimpleNamespace(
        id="question-1",
        type=QuestionType.TRUE_FALSE,
        options=[],
        prompt="Is this sentence correct?",
        media=[],
    )
    state = AppState(questions=[question], finished=True)  # type: ignore[list-item]

    class Controller:
        def session_snapshot(self) -> tuple[str, int]:
            return "token", 1

        def session_is_current(self, token: str, generation: int) -> bool:
            return True

        async def submit(self, question_id: str, response: dict) -> bool:
            return False

        def previous(self) -> None:
            pass

    widget = SimpleNamespace(
        build=lambda value: None,
        extract=lambda: {"selected": True},
        control=login_screen.ft.Container(),
    )

    async def no_audio(page) -> None:
        pass

    routes: list[str] = []
    monkeypatch.setattr(
        question_screen, "use_ref", lambda initial: SimpleNamespace(current=initial)
    )
    monkeypatch.setattr(question_screen, "answer_factory", lambda value: widget)
    monkeypatch.setattr(question_screen, "stop_audio", no_audio)
    monkeypatch.setattr(question_screen, "media_area", lambda *args: [])
    monkeypatch.setattr(
        question_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=routes.append)),
    )

    view = question_screen.QuestionScreen.__wrapped__(state, Controller())
    asyncio.run(_keyed(view, "question-submit").on_click(None))
    assert routes == []


class _DelayedBody(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], delay: float) -> None:
        self.chunks = chunks
        self.delay = delay
        self.cancelled = False

    async def __aiter__(self):
        try:
            for chunk in self.chunks:
                await asyncio.sleep(self.delay)
                yield chunk
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_api_absolute_deadline_cancels_dripping_response_body() -> None:
    stream = _DelayedBody(
        [b'{"access_token":', b'"opaque",', b'"token_type":"bearer"}'],
        delay=0.03,
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    async def exercise() -> QuizApiError:
        api = QuizApiClient(timeout=0.05)
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(QuizApiError) as raised:
                await api.login("09149991680", "password")
            await asyncio.sleep(0.05)
            return raised.value
        finally:
            await api.aclose()

    error = asyncio.run(exercise())

    assert error.status_code == 503
    assert error.code == "auth_unavailable"
    assert stream.cancelled is True


@pytest.mark.parametrize("method_name", ["list_quizzes", "download_report_pdf"])
def test_every_authenticated_body_path_invalidates_once_on_top_level_401(
    method_name: str,
) -> None:
    invalidations: list[tuple[str, int | None]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "auth_required", "message": "sign in"})

    async def exercise() -> None:
        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        api.set_auth_required_handler(
            lambda token, generation: invalidations.append((token, generation)),
            lambda: 7,
        )
        try:
            with pytest.raises(QuizApiError):
                if method_name == "download_report_pdf":
                    await api.download_report_pdf("opaque", "attempt")
                else:
                    await api.list_quizzes("opaque")
        finally:
            await api.aclose()

    asyncio.run(exercise())
    assert invalidations == [("opaque", 7)]


@pytest.mark.parametrize("status", [502, 503])
@pytest.mark.parametrize("method_name", ["list_quizzes", "download_report_pdf"])
def test_authenticated_outage_never_invalidates_local_session(
    status: int, method_name: str
) -> None:
    invalidations: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        code = "auth_invalid_response" if status == 502 else "auth_unavailable"
        return httpx.Response(status, json={"code": code, "message": "retry"})

    async def exercise() -> None:
        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        api.set_auth_required_handler(
            lambda token, generation: invalidations.append(token), lambda: 0
        )
        try:
            with pytest.raises(QuizApiError):
                if method_name == "download_report_pdf":
                    await api.download_report_pdf("opaque", "attempt")
                else:
                    await api.list_quizzes("opaque")
        finally:
            await api.aclose()

    asyncio.run(exercise())
    assert invalidations == []


def test_logout_deadline_still_clears_local_state() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204, stream=_DelayedBody([b""], delay=0.1))

    async def exercise() -> tuple[bool, AppState]:
        api = QuizApiClient(timeout=0.02)
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        state = _authenticated_state()
        auth = AuthController(state, api)
        try:
            return await auth.logout(), state
        finally:
            await api.aclose()

    confirmed, state = asyncio.run(exercise())
    assert confirmed is False
    _assert_local_session_cleared(state)


def _relative_luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_login_error_palette_meets_wcag_aa_for_normal_text() -> None:
    foreground = _relative_luminance(theme.ERROR)
    background = _relative_luminance(theme.ERROR_LIGHT)
    contrast = (max(foreground, background) + 0.05) / (
        min(foreground, background) + 0.05
    )
    assert contrast >= 4.5


class _RevalidationApi:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def me(self, token: str):
        self.calls.append(token)
        if self.error:
            raise self.error
        return self.result


def test_revalidation_refreshes_role_before_marking_route_valid() -> None:
    state = _authenticated_state()
    state.auth_validation_status = "valid"
    state.auth_validation_route = "/quizzes"
    refreshed = SimpleNamespace(email="learner@incluir.test", role=UserRole.STUDENT)
    api = _RevalidationApi(refreshed)
    auth = AuthController(state, api)  # type: ignore[arg-type]

    outcome = asyncio.run(auth.revalidate("/admin/grades", force=True))

    assert outcome == "valid"
    assert state.current_user is refreshed
    assert state.auth_validation_route == "/admin/grades"
    assert state.auth_validation_status == "valid"


def test_revalidation_outage_preserves_auth_but_blocks_cached_render() -> None:
    state = _authenticated_state()
    cached_user = state.current_user
    api = _RevalidationApi(error=QuizApiError(503, "retry", code="auth_unavailable"))
    auth = AuthController(state, api)  # type: ignore[arg-type]

    outcome = asyncio.run(auth.revalidate("/quizzes", force=True))

    assert outcome == "unavailable"
    assert state.token == "opaque-better-auth-cookie"
    assert state.current_user is cached_user
    assert state.auth_validation_status == "unavailable"
    assert state.auth_validation_route == "/quizzes"


def test_late_revalidation_result_cannot_restore_content_after_invalidation() -> None:
    async def scenario() -> tuple[str, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()
        refreshed = SimpleNamespace(email="learner@incluir.test", role=UserRole.STUDENT)

        class BlockingApi:
            async def me(self, token: str):
                started.set()
                await release.wait()
                return refreshed

        state = _authenticated_state()
        auth = AuthController(state, BlockingApi())  # type: ignore[arg-type]
        task = asyncio.create_task(auth.revalidate("/quizzes", force=True))
        await started.wait()
        auth.invalidate_validation()
        release.set()
        return await task, state

    outcome, state = asyncio.run(scenario())
    assert outcome == "stale"
    assert state.auth_validation_status == "unverified"
    assert state.auth_validation_route is None


def test_revalidation_proven_401_clears_complete_session_once() -> None:
    async def scenario() -> tuple[str, AppState, list[str]]:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401, json={"code": "auth_required", "message": "sign in"}
            )

        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        state = _authenticated_state()
        auth = AuthController(state, api)
        invalidations: list[str] = []

        def clear(failed_token: str, failed_generation: int | None) -> None:
            assert failed_token == state.token
            invalidations.append("cleared")
            auth.invalidate_validation()
            state.clear_session()

        api.set_auth_required_handler(clear, lambda: state.auth_session_generation)
        try:
            return await auth.revalidate("/quizzes", force=True), state, invalidations
        finally:
            await api.aclose()

    outcome, state, invalidations = asyncio.run(scenario())
    assert outcome == "invalid"
    assert invalidations == ["cleared"]
    _assert_local_session_cleared(state)


def test_delayed_old_token_401_cannot_clear_new_session() -> None:
    async def scenario() -> tuple[AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            started.set()
            await release.wait()
            return httpx.Response(
                401, json={"code": "auth_required", "message": "sign in"}
            )

        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        state = _authenticated_state()
        state.token = "token-A"
        state.auth_session_generation = 1
        ignored: list[str] = []

        def invalidate_if_current(
            failed_token: str, failed_generation: int | None
        ) -> None:
            if (
                state.token != failed_token
                or state.auth_session_generation != failed_generation
            ):
                ignored.append(failed_token)
                return
            state.clear_session()

        api.set_auth_required_handler(
            invalidate_if_current, lambda: state.auth_session_generation
        )
        request = asyncio.create_task(api.list_quizzes("token-A"))
        await started.wait()
        state.set_authenticated_session(
            "token-B", SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT)
        )
        release.set()
        with pytest.raises(QuizApiError):
            await request
        await api.aclose()
        return state, ignored

    state, ignored = asyncio.run(scenario())
    assert state.token == "token-B"
    assert state.current_user.email == "b@incluir.test"
    assert ignored == ["token-A"]


def test_delayed_login_cannot_replace_a_newer_session() -> None:
    async def scenario() -> tuple[bool, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def login(self, cpf: str, password: str):
                return SimpleNamespace(access_token="login-A-token")

            async def me(self, token: str):
                started.set()
                await release.wait()
                return SimpleNamespace(email="a@incluir.test", role=UserRole.STUDENT)

        state = AppState()
        auth = AuthController(state, Api())  # type: ignore[arg-type]
        task = asyncio.create_task(auth.login("09149991680", "password"))
        await started.wait()
        state.set_authenticated_session(
            "session-B",
            SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT),
        )
        release.set()
        return await task, state

    committed, state = asyncio.run(scenario())
    assert committed is False
    assert state.token == "session-B"
    assert state.current_user.email == "b@incluir.test"


def test_delayed_401_is_rejected_by_generation_when_token_text_is_reused() -> None:
    async def scenario() -> AppState:
        started = asyncio.Event()
        release = asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            started.set()
            await release.wait()
            return httpx.Response(
                401, json={"code": "auth_required", "message": "sign in"}
            )

        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        state = _authenticated_state()
        state.token = "reused-token"
        state.auth_session_generation = 4

        def invalidate_if_current(
            failed_token: str, failed_generation: int | None
        ) -> None:
            if (
                state.token == failed_token
                and state.auth_session_generation == failed_generation
            ):
                state.clear_session()

        api.set_auth_required_handler(
            invalidate_if_current, lambda: state.auth_session_generation
        )
        request = asyncio.create_task(api.list_quizzes("reused-token"))
        await started.wait()
        state.set_authenticated_session(
            "reused-token",
            SimpleNamespace(email="new@incluir.test", role=UserRole.STUDENT),
        )
        release.set()
        with pytest.raises(QuizApiError):
            await request
        await api.aclose()
        return state

    state = asyncio.run(scenario())
    assert state.token == "reused-token"
    assert state.current_user.email == "new@incluir.test"
    assert state.auth_session_generation == 5


def test_delayed_old_quiz_start_cannot_commit_or_navigate_under_new_session() -> None:
    async def scenario() -> tuple[bool, AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()
        navigations: list[str] = []

        class Api:
            async def get_question(self, token: str, question_id: str):
                started.set()
                await release.wait()
                return SimpleNamespace(id=question_id)

            async def start_attempt(self, token: str, quiz_id: str):
                raise AssertionError("stale start reached attempt creation")

        state = _authenticated_state()
        state.token = "token-A"
        state.auth_session_generation = 1
        state.quiz = None
        state.questions = []
        controller = QuizController(state, Api())  # type: ignore[arg-type]
        quiz = SimpleNamespace(id="quiz-A", question_ids=["question-A"])
        task = asyncio.create_task(controller.start(quiz))
        await started.wait()
        state.clear_session()
        state.set_authenticated_session(
            "token-B", SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT)
        )
        release.set()
        committed = await task
        if committed:
            navigations.append("/quiz/0")
        return committed, state, navigations

    committed, state, navigations = asyncio.run(scenario())
    assert committed is False
    assert state.token == "token-B"
    assert state.quiz is None
    assert state.questions == []
    assert state.attempt_id is None
    assert navigations == []


def test_delayed_start_attempt_cannot_commit_when_generation_changes_with_same_token() -> (
    None
):
    async def scenario() -> tuple[bool, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def get_question(self, token: str, question_id: str):
                return SimpleNamespace(id=question_id)

            async def start_attempt(self, token: str, quiz_id: str):
                started.set()
                await release.wait()
                return SimpleNamespace(id="attempt-A")

        state = _authenticated_state()
        state.token = "reused-token"
        state.auth_session_generation = 9
        state.clear_session()
        state.set_authenticated_session(
            "reused-token",
            SimpleNamespace(email="a@incluir.test", role=UserRole.STUDENT),
        )
        controller = QuizController(state, Api())  # type: ignore[arg-type]
        quiz = SimpleNamespace(id="quiz-A", question_ids=["question-A"])
        task = asyncio.create_task(controller.start(quiz))
        await started.wait()
        state.set_authenticated_session(
            "reused-token",
            SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT),
        )
        release.set()
        return await task, state

    committed, state = asyncio.run(scenario())
    assert committed is False
    assert state.current_user.email == "b@incluir.test"
    assert state.quiz is None
    assert state.questions == []
    assert state.attempt_id is None


def test_delayed_old_submit_error_is_ignored_without_state_or_navigation() -> None:
    async def scenario() -> tuple[bool, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def submit_answer(
                self, token: str, attempt_id: str, question_id: str, response: dict
            ) -> None:
                started.set()
                await release.wait()
                raise QuizApiError(503, "old outage", code="auth_unavailable")

        state = _authenticated_state()
        state.token = "reused-token"
        state.auth_session_generation = 12
        state.answers = {}
        state.questions = [object(), object()]  # type: ignore[list-item]
        state.current_index = 0
        controller = QuizController(state, Api())  # type: ignore[arg-type]
        task = asyncio.create_task(
            controller.submit("question-A", {"selected": "answer-A"})
        )
        await started.wait()
        state.clear_session()
        state.set_authenticated_session(
            "reused-token",
            SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT),
        )
        release.set()
        return await task, state

    committed, state = asyncio.run(scenario())
    assert committed is False
    assert state.current_user.email == "b@incluir.test"
    assert state.answers == {}
    assert state.current_index == 0
    assert state.result is None


def test_delayed_old_finish_cannot_restore_result_under_new_session() -> None:
    async def scenario() -> tuple[object | None, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def finish_attempt(self, token: str, attempt_id: str):
                started.set()
                await release.wait()
                return SimpleNamespace(score=4, max_score=4)

        state = _authenticated_state()
        state.token = "token-A"
        state.auth_session_generation = 1
        controller = QuizController(state, Api())  # type: ignore[arg-type]
        task = asyncio.create_task(controller.finish())
        await started.wait()
        state.clear_session()
        state.set_authenticated_session(
            "token-B", SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT)
        )
        release.set()
        return await task, state

    result, state = asyncio.run(scenario())
    assert result is None
    assert state.token == "token-B"
    assert state.result is None
    assert state.finished is False


def test_delayed_old_logout_finalizer_cannot_clear_or_navigate_new_session() -> None:
    async def scenario() -> tuple[bool, AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()
        navigations: list[str] = []

        class Api:
            async def logout(self, token: str) -> None:
                started.set()
                await release.wait()

        state = _authenticated_state()
        state.token = "token-A"
        state.auth_session_generation = 1
        auth = AuthController(state, Api())  # type: ignore[arg-type]
        task = asyncio.create_task(auth.logout())
        await started.wait()
        state.set_authenticated_session(
            "token-B", SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT)
        )
        release.set()
        confirmed = await task
        if state.token is None:
            navigations.append("/")
        return confirmed, state, navigations

    confirmed, state, navigations = asyncio.run(scenario())
    assert confirmed is True
    assert state.token == "token-B"
    assert state.current_user.email == "b@incluir.test"
    assert navigations == []


def test_disconnect_directly_replaces_retained_tree_with_neutral_view() -> None:
    state = _authenticated_state()
    state.auth_session_generation = 7
    retained_user = state.current_user
    state.auth_validation_status = "valid"
    state.auth_validation_route = "/quizzes"
    auth = SimpleNamespace(
        invalidate_validation=lambda: state.invalidate_auth_validation()
    )
    updates: list[str] = []
    page = SimpleNamespace(
        route="/quizzes",
        views=[SimpleNamespace(key="retained-protected-picker")],
        update=lambda: updates.append("updated"),
    )

    install_session_revalidation(page, state, auth)  # type: ignore[arg-type]
    page.on_disconnect(None)

    assert state.token == "opaque-better-auth-cookie"
    assert state.current_user is retained_user
    assert state.auth_session_generation == 8
    assert state.auth_validation_status == "unverified"
    assert state.auth_validation_route is None
    assert len(page.views) == 1
    assert _keyed(page.views[0], "auth-check-loading") is not None
    assert not any(
        getattr(control, "key", None) == "retained-protected-picker"
        for control in _walk_controls(page.views[0])
    )
    assert updates == ["updated"]


def test_disconnect_revokes_in_flight_anonymous_login_ownership() -> None:
    async def scenario() -> tuple[bool, AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def login(self, cpf: str, password: str):
                return SimpleNamespace(access_token="late-token")

            async def me(self, token: str):
                started.set()
                await release.wait()
                return SimpleNamespace(email="late@incluir.test", role=UserRole.STUDENT)

        state = AppState()
        auth = AuthController(state, Api())  # type: ignore[arg-type]
        updates: list[str] = []
        page = SimpleNamespace(route="/", update=lambda: updates.append("updated"))
        install_session_revalidation(page, state, auth)
        login = asyncio.create_task(auth.login("09149991680", "password"))
        await started.wait()
        page.on_disconnect(None)
        release.set()
        return await login, state, updates

    committed, state, updates = asyncio.run(scenario())
    assert committed is False
    assert state.auth_session_generation == 1
    assert state.token is None
    assert state.current_user is None
    assert updates == []


@pytest.mark.parametrize(
    ("token", "user"),
    [
        ("partial-token", None),
        (None, SimpleNamespace(role=UserRole.STUDENT)),
    ],
)
def test_disconnect_advances_work_epoch_for_partial_auth_state(
    token: str | None, user: object | None
) -> None:
    state = AppState(token=token)
    state.current_user = user  # type: ignore[assignment]
    auth = SimpleNamespace(
        invalidate_validation=lambda: state.invalidate_auth_validation()
    )
    updates: list[str] = []
    page = SimpleNamespace(route="/", update=lambda: updates.append("updated"))

    install_session_revalidation(page, state, auth)  # type: ignore[arg-type]
    page.on_disconnect(None)

    assert state.auth_session_generation == 1
    assert state.token == token
    assert state.current_user is user
    assert updates == []


def test_reconnect_forces_authoritative_check_only_for_protected_route() -> None:
    state = _authenticated_state()
    calls: list[tuple[str, bool]] = []
    restores: list[str] = []

    class FakeAuth:
        def invalidate_validation(self) -> None:
            pass

        async def revalidate(self, route: str, *, force: bool = False) -> None:
            calls.append((route, force))

    page = SimpleNamespace(route="/results", update=lambda: None)
    install_session_revalidation(  # type: ignore[arg-type]
        page, state, FakeAuth(), lambda: restores.append(page.route)
    )
    asyncio.run(page.on_connect(None))
    page.route = "/"
    asyncio.run(page.on_connect(None))

    assert calls == [("/results", True)]
    assert restores == ["/results"]


def test_route_mismatch_guard_never_invokes_protected_render(monkeypatch) -> None:
    state = _authenticated_state()
    state.auth_validation_status = "valid"
    state.auth_validation_route = "/quizzes"
    page = SimpleNamespace(route="/admin/grades", navigate=lambda route: None)
    monkeypatch.setattr(auth_guard.ft, "context", SimpleNamespace(page=page))
    monkeypatch.setattr(auth_guard, "_AuthCheck", lambda *args: "auth-gate")

    def forbidden_render():
        raise AssertionError("protected content rendered before /users/me")

    control = auth_guard.AuthGuard.__wrapped__(
        state, SimpleNamespace(), forbidden_render, admin_only=True
    )
    assert control == "auth-gate"


def test_refreshed_role_downgrade_redirects_before_admin_render(monkeypatch) -> None:
    state = _authenticated_state()
    state.current_user = SimpleNamespace(role=UserRole.STUDENT)  # type: ignore[assignment]
    state.auth_validation_status = "valid"
    state.auth_validation_route = "/admin/grades"
    page = SimpleNamespace(route="/admin/grades", navigate=lambda route: None)
    monkeypatch.setattr(auth_guard.ft, "context", SimpleNamespace(page=page))
    monkeypatch.setattr(auth_guard, "_redirecting", lambda route: ("redirect", route))

    def forbidden_render():
        raise AssertionError("downgraded role rendered admin content")

    control = auth_guard.AuthGuard.__wrapped__(
        state, SimpleNamespace(), forbidden_render, admin_only=True
    )
    assert control == ("redirect", "/quizzes")


def test_unavailable_gate_has_live_named_retry_and_no_protected_content(
    monkeypatch,
) -> None:
    state = _authenticated_state()
    state.auth_validation_status = "unavailable"
    state.auth_validation_route = "/quizzes"
    state.auth_validation_message = "Não foi possível verificar sua sessão."
    monkeypatch.setattr(auth_guard, "use_effect", lambda callback, deps: None)

    view = auth_guard._AuthCheck.__wrapped__(
        state, SimpleNamespace(revalidate=lambda *args, **kwargs: None), "/quizzes"
    )
    retry = _keyed(view, "auth-check-retry")
    semantics = [
        item
        for item in _walk_controls(view)
        if isinstance(item, login_screen.ft.Semantics)
    ]
    assert retry.height >= 44
    assert callable(retry.on_click)
    assert any(item.live_region for item in semantics)


def test_login_submit_and_password_eye_callbacks_change_state_and_navigate(
    monkeypatch,
) -> None:
    setter_values: list[tuple[str, object]] = []
    password_ref = SimpleNamespace(current="secret")
    hook_values = iter(
        [
            ("091.499.916-80", lambda value: setter_values.append(("cpf", value))),
            (False, lambda value: setter_values.append(("eye", value))),
            ("", lambda value: setter_values.append(("error", value))),
            (False, lambda value: setter_values.append(("loading", value))),
        ]
    )
    state = AppState(return_route="/quizzes")
    validated: list[str] = []

    class FakeAuth:
        def __init__(self) -> None:
            self.state = state

        async def login(self, cpf: str, password: str) -> bool:
            assert (cpf, password) == ("09149991680", "secret")
            self.state.current_user = SimpleNamespace(role=UserRole.STUDENT)
            return True

        def mark_validated_route(self, route: str) -> None:
            validated.append(route)

    routes: list[str] = []
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=routes.append
    )
    monkeypatch.setattr(login_screen, "use_state", lambda initial: next(hook_values))
    monkeypatch.setattr(login_screen, "use_ref", lambda initial: password_ref)
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(FakeAuth())
    eye = _keyed(view, "login-password-visibility")
    submit = _keyed(view, "login-submit")
    eye.on_click(None)
    asyncio.run(submit.on_click(None))

    assert ("eye", True) in setter_values
    assert validated == ["/quizzes"]
    assert routes == ["/quizzes"]


def test_password_keystrokes_keep_browser_buffer_until_reveal_and_submit(
    monkeypatch,
) -> None:
    password_ref = SimpleNamespace(current="")
    setter_values: list[tuple[str, object]] = []
    state = AppState(return_route="/quizzes")
    received: list[tuple[str, str]] = []

    class FakeAuth:
        def __init__(self) -> None:
            self.state = state

        async def login(self, cpf: str, password: str) -> bool:
            received.append((cpf, password))
            self.state.current_user = SimpleNamespace(role=UserRole.STUDENT)
            return True

        def mark_validated_route(self, route: str) -> None:
            pass

    routes: list[str] = []
    page = SimpleNamespace(
        title="", route="/", update=lambda: None, navigate=routes.append
    )
    monkeypatch.setattr(login_screen, "use_ref", lambda initial: password_ref)
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    def render(*, password_visible: bool):
        hook_values = iter(
            [
                (
                    "091.499.916-80",
                    lambda value: setter_values.append(("cpf", value)),
                ),
                (
                    password_visible,
                    lambda value: setter_values.append(("eye", value)),
                ),
                ("", lambda value: setter_values.append(("error", value))),
                (False, lambda value: setter_values.append(("loading", value))),
            ]
        )
        monkeypatch.setattr(
            login_screen, "use_state", lambda initial: next(hook_values)
        )
        return login_screen.LoginScreen.__wrapped__(FakeAuth())

    first_view = render(password_visible=False)
    password_field = _keyed(first_view, "login-password")
    final_value = "typing-sequence"
    for index in range(1, len(final_value) + 1):
        password_field.on_change(
            SimpleNamespace(control=SimpleNamespace(value=final_value[:index]))
        )

    assert password_ref.current == final_value
    assert setter_values == []

    _keyed(first_view, "login-password-visibility").on_click(None)
    assert setter_values == [("eye", True)]

    revealed_view = render(password_visible=True)
    revealed_password = _keyed(revealed_view, "login-password")
    assert revealed_password.value == final_value
    assert revealed_password.password is False

    asyncio.run(_keyed(revealed_view, "login-submit").on_click(None))

    assert received == [("09149991680", final_value)]
    assert routes == ["/quizzes"]


def test_account_menu_destinations_and_logout_callbacks_navigate(monkeypatch) -> None:
    state = AppState(email="admin@incluir.test")
    state.current_user = SimpleNamespace(role=UserRole.ADMIN)  # type: ignore[assignment]
    logouts: list[str] = []

    class FakeAuth:
        def __init__(self, app_state: AppState) -> None:
            self.state = app_state

        async def logout(self) -> bool:
            logouts.append("logout")
            return True

    routes: list[str] = []
    page = SimpleNamespace(navigate=routes.append)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    bar = app_bar(state, FakeAuth(state))  # type: ignore[arg-type]
    _keyed(bar, "account-quizzes").on_click(None)
    _keyed(bar, "account-admin-grades").on_click(None)
    asyncio.run(_keyed(bar, "account-logout").on_click(None))

    assert routes == ["/quizzes", "/admin/grades", "/"]
    assert logouts == ["logout"]


def test_results_callbacks_navigate_and_download(monkeypatch) -> None:
    state = AppState(attempt_id="attempt-1")
    state.result = SimpleNamespace(score=4, max_score=4)  # type: ignore[assignment]
    downloads: list[tuple[str, bytes]] = []

    class Controller:
        async def download_report(self) -> bytes:
            return b"%PDF"

    async def save(name: str, value: bytes) -> None:
        downloads.append((name, value))

    routes: list[str] = []
    monkeypatch.setattr(
        results_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=routes.append)),
    )
    monkeypatch.setattr(results_screen, "save_bytes", save)

    view = results_screen.ResultsScreen.__wrapped__(state, Controller())
    _keyed(view, "results-take-another").on_click(None)
    asyncio.run(_keyed(view, "results-download").on_click(None))

    assert routes == ["/quizzes"]
    assert downloads == [("quiz-report-attempt-1.pdf", b"%PDF")]


def test_admin_quiz_row_is_native_keyboard_action_with_canonical_level(
    monkeypatch,
) -> None:
    quiz = SimpleNamespace(
        id="quiz-1",
        title="Intermediate Check",
        category="reading",
        level=SimpleNamespace(value="B1"),
        question_ids=["q1"],
    )
    hooks = iter(
        [
            ([quiz], lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    routes: list[str] = []
    monkeypatch.setattr(admin_quiz_list_screen, "use_state", lambda value: next(hooks))
    monkeypatch.setattr(
        admin_quiz_list_screen,
        "use_ref",
        lambda value: SimpleNamespace(current=value),
    )
    monkeypatch.setattr(admin_quiz_list_screen, "use_effect", lambda *args: None)
    monkeypatch.setattr(
        admin_quiz_list_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=routes.append)),
    )
    state = AppState(email="admin@incluir.test")
    state.current_user = SimpleNamespace(role=UserRole.ADMIN)  # type: ignore[assignment]

    view = admin_quiz_list_screen.AdminQuizListScreen.__wrapped__(
        state, SimpleNamespace(), SimpleNamespace()
    )
    row = _keyed(view, "admin-quiz-row-quiz-1")
    row.on_click(None)
    state.supersede_async_work()
    row.on_click(None)

    assert isinstance(row, login_screen.ft.Button)
    assert routes == ["/admin/grades/quiz-1"]
    assert any("B1" in value for value in _text_values(view))
    assert all("namespace" not in value for value in _text_values(view))


def test_admin_filter_callback_and_mutually_exclusive_error_classifier(
    monkeypatch,
) -> None:
    selected: list[str] = []
    hooks = iter(
        [
            ("", selected.append),
            ([], lambda value: None),
            ([], lambda value: None),
            (False, lambda value: None),
            ("", lambda value: None),
            (False, lambda value: None),
        ]
    )
    monkeypatch.setattr(admin_grades_screen, "use_state", lambda value: next(hooks))
    monkeypatch.setattr(admin_grades_screen, "use_effect", lambda *args: None)
    monkeypatch.setattr(
        admin_grades_screen, "use_ref", lambda value: SimpleNamespace(current=value)
    )
    monkeypatch.setattr(
        admin_grades_screen, "use_route_params", lambda: {"quiz_id": "quiz-1"}
    )
    monkeypatch.setattr(
        admin_grades_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=lambda route: None)),
    )
    monkeypatch.setattr(admin_grades_screen, "_build_boxplot_png", lambda items: "")
    monkeypatch.setattr(
        admin_grades_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=lambda route: None)),
    )
    state = AppState(email="admin@incluir.test")
    state.current_user = SimpleNamespace(role=UserRole.ADMIN)  # type: ignore[assignment]

    view = admin_grades_screen.AdminGradesScreen.__wrapped__(
        state, SimpleNamespace(), SimpleNamespace()
    )
    level_filter = _keyed(view, "admin-level-filter")
    b2_option = _keyed(view, "admin-level-option-B2")
    b2_option.on_click(None)

    assert selected == ["B2"]
    assert isinstance(level_filter, admin_grades_screen.ft.Column)
    assert "Class (level)" in _text_values(level_filter)
    assert _keyed(view, "admin-level-option-all").content == "All"
    assert b2_option.height >= 44
    assert b2_option.content == "B2"
    assert isinstance(b2_option, admin_grades_screen.ft.OutlinedButton)
    assert admin_grades_screen.classify_load_error(QuizApiError(403, "denied")) == (
        True,
        "",
    )
    forbidden, message = admin_grades_screen.classify_load_error(
        QuizApiError(500, "outage")
    )
    assert forbidden is False
    assert "outage" in message


def test_new_authenticated_session_clears_all_prior_quiz_owned_state() -> None:
    state = _authenticated_state()
    previous_generation = state.auth_session_generation

    state.set_authenticated_session(
        state.token,
        SimpleNamespace(email="new@incluir.test", role=UserRole.STUDENT),
    )

    assert state.auth_session_generation == previous_generation + 1
    assert state.current_user.email == "new@incluir.test"
    assert state.quiz is None
    assert state.questions == []
    assert state.answers == {}
    assert state.current_index == 0
    assert state.attempt_id is None
    assert state.finished is False
    assert state.result is None


def test_pre_disconnect_401_cannot_clear_same_token_revalidated_session() -> None:
    async def scenario() -> tuple[AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            started.set()
            await release.wait()
            return httpx.Response(
                401, json={"code": "auth_required", "message": "sign in"}
            )

        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        state = _authenticated_state()
        state.auth_session_generation = 20
        auth = AuthController(state, api)
        routes: list[str] = []
        page = SimpleNamespace(
            route="/quizzes", update=lambda: None, navigate=routes.append
        )
        api.set_auth_required_handler(
            lambda token, generation: handle_auth_required(
                page, state, auth, token, generation
            ),
            lambda: state.auth_session_generation,
        )
        install_session_revalidation(page, state, auth)

        old_request = asyncio.create_task(api.list_quizzes(state.token))
        await started.wait()
        page.on_disconnect(None)
        auth.mark_validated_route("/quizzes")
        release.set()
        with pytest.raises(QuizApiError):
            await old_request
        await api.aclose()
        return state, routes

    state, routes = asyncio.run(scenario())
    assert state.token == "opaque-better-auth-cookie"
    assert state.auth_session_generation == 21
    assert state.auth_validation_status == "valid"
    assert state.auth_validation_route == "/quizzes"
    assert routes == []


@pytest.mark.parametrize("operation", ["start", "submit", "finish"])
def test_pre_disconnect_quiz_success_cannot_commit_same_token_work(
    operation: str,
) -> None:
    async def scenario() -> tuple[object, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        class Api:
            async def get_question(self, token: str, question_id: str):
                return SimpleNamespace(id=question_id)

            async def start_attempt(self, token: str, quiz_id: str):
                started.set()
                await release.wait()
                return SimpleNamespace(id="old-attempt")

            async def submit_answer(
                self, token: str, attempt_id: str, question_id: str, response: dict
            ) -> None:
                started.set()
                await release.wait()

            async def finish_attempt(self, token: str, attempt_id: str):
                started.set()
                await release.wait()
                return SimpleNamespace(score=4, max_score=4)

        state = _authenticated_state()
        state.auth_session_generation = 30
        if operation == "start":
            state._clear_quiz_state()
        elif operation == "submit":
            state.answers = {}
            state.questions = [object(), object()]  # type: ignore[list-item]
            state.current_index = 0
            state.finished = False
            state.result = None
        else:
            state.finished = False
            state.result = None
        controller = QuizController(state, Api())  # type: ignore[arg-type]

        if operation == "start":
            work = asyncio.create_task(
                controller.start(
                    SimpleNamespace(id="quiz-A", question_ids=["question-A"])
                )
            )
        elif operation == "submit":
            work = asyncio.create_task(
                controller.submit("question-A", {"selected": "answer-A"})
            )
        else:
            work = asyncio.create_task(controller.finish())

        await started.wait()
        page = SimpleNamespace(route="/quizzes", update=lambda: None)
        auth = SimpleNamespace(
            invalidate_validation=lambda: state.invalidate_auth_validation()
        )
        install_session_revalidation(page, state, auth)  # type: ignore[arg-type]
        page.on_disconnect(None)
        release.set()
        return await work, state

    result, state = asyncio.run(scenario())
    assert result is False or result is None
    assert state.token == "opaque-better-auth-cookie"
    assert state.auth_session_generation == 31
    if operation == "start":
        assert state.quiz is None
        assert state.questions == []
        assert state.attempt_id is None
    elif operation == "submit":
        assert state.answers == {}
        assert state.current_index == 0
        assert state.result is None
    else:
        assert state.finished is False
        assert state.result is None


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("list_quizzes", ()),
        ("list_attempts", ("quiz-A", None)),
        ("get_question_stats", ("quiz-A", None)),
    ],
)
@pytest.mark.parametrize("raises", [False, True])
def test_admin_controller_ignores_stale_success_and_error(
    method_name: str, args: tuple, raises: bool
) -> None:
    async def scenario() -> tuple[object, AppState]:
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed(*args, **kwargs):
            started.set()
            await release.wait()
            if raises:
                raise QuizApiError(401, "old session", code="auth_required")
            return [SimpleNamespace(id="old-data")]

        api = SimpleNamespace(
            list_quizzes=delayed,
            admin_list_attempts=delayed,
            admin_question_stats=delayed,
        )
        state = _authenticated_state()
        state.auth_session_generation = 40
        controller = AdminController(state, api)  # type: ignore[arg-type]
        task = asyncio.create_task(getattr(controller, method_name)(*args))
        await started.wait()
        state.supersede_async_work()
        release.set()
        return await task, state

    result, state = asyncio.run(scenario())
    assert result is None
    assert state.token == "opaque-better-auth-cookie"
    assert state.auth_session_generation == 41


def test_question_audio_wait_loses_action_authority_on_disconnect(monkeypatch) -> None:
    async def scenario(action_key: str) -> tuple[AppState, list[str]]:
        started = asyncio.Event()
        release = asyncio.Event()
        submits: list[str] = []
        routes: list[str] = []
        question = SimpleNamespace(
            id="question-1",
            type=QuestionType.TRUE_FALSE,
            options=[],
            prompt="Is this sentence correct?",
            media=[],
        )
        state = AppState(questions=[question], token="token-A")  # type: ignore[list-item]
        state.current_user = SimpleNamespace(role=UserRole.STUDENT)  # type: ignore[assignment]
        state.auth_session_generation = 50

        class Api:
            async def submit_answer(self, *args, **kwargs):
                submits.append("submitted")

        controller = QuizController(state, Api())  # type: ignore[arg-type]
        widget = SimpleNamespace(
            build=lambda value: None,
            extract=lambda: {"selected": True},
            control=login_screen.ft.Container(),
        )

        async def blocked_audio(page) -> None:
            started.set()
            await release.wait()

        monkeypatch.setattr(
            question_screen,
            "use_ref",
            lambda initial: SimpleNamespace(current=initial),
        )
        monkeypatch.setattr(question_screen, "answer_factory", lambda value: widget)
        monkeypatch.setattr(question_screen, "stop_audio", blocked_audio)
        monkeypatch.setattr(question_screen, "media_area", lambda *args: [])
        page = SimpleNamespace(
            route="/quiz/0", navigate=routes.append, update=lambda: None
        )
        monkeypatch.setattr(question_screen.ft, "context", SimpleNamespace(page=page))
        view = question_screen.QuestionScreen.__wrapped__(state, controller)
        action = asyncio.create_task(_keyed(view, action_key).on_click(None))
        await started.wait()
        auth = SimpleNamespace(
            invalidate_validation=lambda: state.invalidate_auth_validation()
        )
        install_session_revalidation(page, state, auth)  # type: ignore[arg-type]
        page.on_disconnect(None)
        release.set()
        await action
        return state, submits + routes

    for key in ("question-back", "question-submit"):
        state, effects = asyncio.run(scenario(key))
        assert state.auth_session_generation == 51
        assert state.current_index == 0
        assert effects == []


def test_admin_quiz_list_drops_stale_local_success_and_error_commits(
    monkeypatch,
) -> None:
    async def run_case(*, raises: bool) -> list[tuple[str, object]]:
        started = asyncio.Event()
        release = asyncio.Event()
        effects: list = []
        commits: list[tuple[str, object]] = []
        state = AppState(token="same-token")
        state.current_user = SimpleNamespace(role=UserRole.ADMIN)  # type: ignore[assignment]
        state.auth_session_generation = 60

        class Controller:
            async def list_quizzes(self):
                started.set()
                await release.wait()
                if raises:
                    raise QuizApiError(503, "old outage", code="auth_unavailable")
                return [SimpleNamespace(id="old-quiz")]

        hooks = iter(
            [
                ([], lambda value: commits.append(("quizzes", value))),
                ("", lambda value: commits.append(("error", value))),
                (True, lambda value: commits.append(("loading", value))),
            ]
        )
        monkeypatch.setattr(
            admin_quiz_list_screen, "use_state", lambda value: next(hooks)
        )
        monkeypatch.setattr(
            admin_quiz_list_screen,
            "use_ref",
            lambda value: SimpleNamespace(current=value),
        )
        monkeypatch.setattr(
            admin_quiz_list_screen,
            "use_effect",
            lambda callback, deps: effects.append(callback),
        )
        monkeypatch.setattr(
            admin_quiz_list_screen.ft,
            "context",
            SimpleNamespace(page=SimpleNamespace(navigate=lambda route: None)),
        )
        admin_quiz_list_screen.AdminQuizListScreen.__wrapped__(
            state, Controller(), SimpleNamespace()
        )
        work = asyncio.create_task(effects[0]())
        await started.wait()
        state.supersede_async_work()
        release.set()
        await work
        return commits

    assert asyncio.run(run_case(raises=False)) == []
    assert asyncio.run(run_case(raises=True)) == []


def test_admin_grades_masks_stale_local_data_and_errors(monkeypatch) -> None:
    stale_attempt = SimpleNamespace(
        finished=True, score=4, level="B1", email="old@incluir.test"
    )
    hooks = iter(
        [
            ("", lambda value: None),
            ([stale_attempt], lambda value: None),
            ([], lambda value: None),
            (False, lambda value: None),
            ("old outage", lambda value: None),
            (True, lambda value: None),
        ]
    )
    refs = iter(
        [
            SimpleNamespace(current=None),
            SimpleNamespace(current=("same-token", 70)),
        ]
    )
    monkeypatch.setattr(admin_grades_screen, "use_state", lambda value: next(hooks))
    monkeypatch.setattr(admin_grades_screen, "use_ref", lambda value: next(refs))
    monkeypatch.setattr(admin_grades_screen, "use_effect", lambda *args: None)
    monkeypatch.setattr(
        admin_grades_screen, "use_route_params", lambda: {"quiz_id": "quiz-1"}
    )
    monkeypatch.setattr(
        admin_grades_screen.ft,
        "context",
        SimpleNamespace(page=SimpleNamespace(navigate=lambda route: None)),
    )
    state = AppState(token="same-token")
    state.current_user = SimpleNamespace(role=UserRole.ADMIN)  # type: ignore[assignment]
    state.auth_session_generation = 71

    view = admin_grades_screen.AdminGradesScreen.__wrapped__(
        state, SimpleNamespace(), SimpleNamespace()
    )
    text = _text_values(view)
    assert "Loading grades..." in text
    assert "old outage" not in text
    assert "You don't have access to the admin dashboard." not in text
    assert "old@incluir.test" not in text
