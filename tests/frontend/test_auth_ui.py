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
from main import canonicalize_client_ip  # noqa: E402
import screens.login as login_screen  # noqa: E402
from screens.login import (  # noqa: E402
    format_cpf,
    login_error_message,
    normalize_cpf_digits,
)
from services.exceptions import QuizApiError  # noqa: E402
from services.api import QuizApiClient  # noqa: E402
from state.app_state import AppState, resolve_return_route  # noqa: E402
from quiz_shared.enums import QuestionType, UserRole  # noqa: E402
from widgets.answers.answer_factory import answer_factory  # noqa: E402
from widgets.navbar import app_bar  # noqa: E402
import screens.picker as picker_screen  # noqa: E402
import screens.question as question_screen  # noqa: E402
import screens.results as results_screen  # noqa: E402


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
            "https://quiz.example.test",
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
            "https://quiz.example.test",
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


def test_login_error_mapping_accepts_fastapi_nested_detail() -> None:
    error = QuizApiError(403, {"code": "account_denied"})

    assert login_error_message(error) == ("Esta conta não pode acessar o Incluir Quiz.")


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
    api = QuizApiClient("https://quiz.example.test")

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
    api = QuizApiClient("https://quiz.example.test")
    api.set_auth_required_handler(lambda: invalidations.append("invalidated"))
    response = httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://quiz.example.test/api/v1/quizzes"),
        json={"code": code, "message": "safe backend message"},
    )

    with pytest.raises(QuizApiError):
        api._handle(response)

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
        api = QuizApiClient("https://quiz.example.test")
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
        api = QuizApiClient("https://quiz.example.test")
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
    monkeypatch.setattr(login_screen, "use_effect", lambda callback, deps: None)
    monkeypatch.setattr(login_screen.ft, "context", SimpleNamespace(page=page))

    view = login_screen.LoginScreen.__wrapped__(auth)

    cpf = _keyed(view, "login-cpf")
    password = _keyed(view, "login-password")
    password_visibility = _keyed(view, "login-password-visibility")
    submit = _keyed(view, "login-submit")
    status = _keyed(view, "login-status")
    semantics = [
        item
        for item in _walk_controls(view)
        if isinstance(item, login_screen.ft.Semantics)
    ]

    assert cpf.label == "CPF"
    assert cpf.keyboard_type == login_screen.ft.KeyboardType.NUMBER
    assert cpf.size_constraints.min_height >= 44
    assert password.label == "Senha"
    assert password.password is True
    assert password.size_constraints.min_height >= 44
    assert password_visibility.tooltip == "Mostrar senha"
    assert password_visibility.width >= 44
    assert password_visibility.height >= 44
    assert submit.height >= 44
    assert "Entrar no Quiz" in _text_values(submit)
    assert any(item.label == "Mostrar senha" and item.button for item in semantics)
    assert any(item.live_region and item.content is status for item in semantics)


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
    assert any(item.label == "Conta" and item.button for item in semantics)


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
    controller = SimpleNamespace()
    page = SimpleNamespace(navigate=lambda route: None)
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

    card = _keyed(view, "quiz-card-quiz-1")
    assert isinstance(card, login_screen.ft.Semantics)
    assert card.label == "Abrir quiz Intermediate Check"
    assert card.button is True
    assert card.container is True
