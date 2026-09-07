"""Phase A contract tests for the Quiz-to-BetterAuth authentication relay."""

from __future__ import annotations

import json
import importlib
import sys
import unittest
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from starlette.requests import Request


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "backend"))
sys.path.insert(0, str(REPO_ROOT / "app" / "shared"))

from app.api.auth_errors import (  # noqa: E402
    AuthAPIError,
    auth_api_error_handler,
    translate_auth_error,
)

auth_routes = importlib.import_module("app.api.routes.auth")
users_routes = importlib.import_module("app.api.routes.users")
from app.api.deps import get_current_user  # noqa: E402
from app.core import monorepo_auth  # noqa: E402
from app.core.client_ip import ORIGINAL_CLIENT_SCOPE_KEY  # noqa: E402
from app.core.cpf import is_valid_cpf, normalize_cpf  # noqa: E402
from app.core.monorepo_auth import (  # noqa: E402
    AuthFailureKind,
    AuthenticatedSession,
    MonorepoAuthError,
    SessionState,
)
from quiz_shared.enums import CourseLevel, UserRole  # noqa: E402
from quiz_shared.schemas import (  # noqa: E402
    AdminAttemptRow,
    AuthErrorCode,
    UserRead,
)


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _json_response(
    status_code: int,
    body: object,
    *,
    headers: list[tuple[str, str]] | dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(status_code, json=body, headers=headers)


def _mock_auth_client(
    handler: Callable[[httpx.Request], httpx.Response],
):
    """Replace only the auth module's client constructor with MockTransport."""

    transport = httpx.MockTransport(handler)

    def factory(*_args, **_kwargs) -> httpx.AsyncClient:
        return _REAL_ASYNC_CLIENT(transport=transport)

    return patch.object(monorepo_auth.httpx, "AsyncClient", side_effect=factory)


def _form_request(
    body: bytes,
    *,
    content_type: bytes = b"application/x-www-form-urlencoded",
    peer: tuple[str, int] | None = ("198.51.100.10", 43100),
) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/token",
        "raw_path": b"/api/v1/auth/token",
        "query_string": b"",
        "headers": [(b"content-type", content_type)],
        "client": peer,
        "server": ("quiz.test", 80),
        ORIGINAL_CLIENT_SCOPE_KEY: peer,
    }
    return Request(scope, receive)


def _login_form(username: str, password: str = "test-input") -> bytes:
    return urlencode({"username": username, "password": password}).encode()


class CpfContractTests(unittest.TestCase):
    def test_accepts_only_approved_ascii_shapes_with_valid_checksum(self) -> None:
        cases = {
            "09149991680": "09149991680",
            "091.499.916-80": "09149991680",
            "  10323969623\t": "10323969623",
            "\n103.239.696-23 ": "10323969623",
            "52998224725": "52998224725",
        }
        for supplied, normalized in cases.items():
            with self.subTest(supplied=supplied):
                self.assertEqual(normalize_cpf(supplied), normalized)
                self.assertTrue(is_valid_cpf(normalized))

    def test_rejects_wrong_shape_repetition_unicode_and_checksum(self) -> None:
        rejected = (
            "",
            "0914999168",
            "091499916800",
            "091 499 916 80",
            "091.499.916/80",
            "x09149991680",
            "09149991680x",
            "00000000000",
            "11111111111",
            "09149991681",
            "٠٩١٤٩٩٩١٦٨٠",
            "０９１４９９９１６８０",
        )
        for supplied in rejected:
            with self.subTest(supplied=supplied):
                self.assertIsNone(normalize_cpf(supplied))


class AuthenticatedEmailEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_users_me_serializes_fixture_identity(self) -> None:
        now = datetime.now(UTC)
        user = {
            "id": uuid4(),
            "email": "e2e-geovana@incluir.test",
            "level": CourseLevel.B1,
            "role": UserRole.STUDENT,
            "created_at": now,
            "updated_at": now,
        }

        async def verified_user() -> dict:
            return user

        endpoint_app = FastAPI()
        endpoint_app.include_router(users_routes.router, prefix="/api/v1/users")
        endpoint_app.dependency_overrides[get_current_user] = verified_user
        transport = httpx.ASGITransport(app=endpoint_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://quiz.test"
        ) as client:
            response = await client.get("/api/v1/users/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], user["email"])


class AuthenticatedEmailResponseTests(unittest.TestCase):
    def test_user_response_accepts_fixture_and_normal_identity_domains(self) -> None:
        now = datetime.now(UTC)
        for email in (
            "e2e-geovana@incluir.test",
            "e2e-admin@incluir.test",
            "learner@example.com",
        ):
            with self.subTest(email=email):
                result = UserRead.model_validate(
                    {
                        "id": uuid4(),
                        "email": email,
                        "level": CourseLevel.B1,
                        "role": UserRole.STUDENT,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                self.assertEqual(result.email, email)

    def test_admin_row_accepts_fixture_and_normal_identity_domains(self) -> None:
        for email in ("e2e-admin@incluir.test", "admin@example.com"):
            with self.subTest(email=email):
                result = AdminAttemptRow.model_validate(
                    {
                        "attempt_id": uuid4(),
                        "user_id": uuid4(),
                        "email": email,
                        "level": CourseLevel.B1,
                        "score": 1.0,
                        "max_score": 1.0,
                        "finished": True,
                    }
                )
                self.assertEqual(result.email, email)

    def test_output_email_rejects_bad_length_whitespace_and_controls(self) -> None:
        now = datetime.now(UTC)
        for email in (
            "",
            "a" * 255,
            "user\texample.com",
            "user\n@example.com",
            "user\r@example.com",
            "user\x1b@example.com",
            "a\x7fb",
            "user\u2028@example.com",
            "user\u2029@example.com",
            "user\u202e@example.com",
            "user\u2066@example.com",
        ):
            with self.subTest(email=email), self.assertRaises(ValueError):
                UserRead.model_validate(
                    {
                        "id": uuid4(),
                        "email": email,
                        "level": CourseLevel.B1,
                        "role": UserRole.STUDENT,
                        "created_at": now,
                        "updated_at": now,
                    }
                )


class MonorepoSignInContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_exact_cpf_payload_and_single_ip_then_joins_verified_email(
        self,
    ) -> None:
        requests: list[httpx.Request] = []
        cookie_pair = "better-auth.session_token=opaque%2Ftoken%3Dvalue"

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/auth/sign-in/email":
                return _json_response(
                    200,
                    {
                        "user": {"email": "untrusted-sign-in-body@example.test"},
                        "session": {"id": "new-session"},
                    },
                    headers=[
                        (
                            "set-cookie",
                            f"{cookie_pair}; Path=/; HttpOnly; SameSite=Lax",
                        ),
                        ("set-cookie", "better-auth.dont_remember=1; Path=/"),
                    ],
                )
            self.assertEqual(request.url.path, "/api/auth/get-session")
            self.assertEqual(request.headers["cookie"], cookie_pair)
            return _json_response(
                200,
                {
                    "session": {"id": "new-session"},
                    "user": {"email": "Verified.User@Example.test"},
                },
            )

        with _mock_auth_client(handler):
            result = await monorepo_auth.sign_in(
                "09149991680", "not-logged", "203.0.113.91"
            )

        self.assertEqual(result.cookie, cookie_pair)
        self.assertEqual(result.email, "Verified.User@example.test")
        self.assertEqual(len(requests), 2)
        sign_in_request = requests[0]
        self.assertEqual(
            json.loads(sign_in_request.content),
            {"cpf": "09149991680", "password": "not-logged"},
        )
        self.assertEqual(
            sign_in_request.headers.get_list("x-forwarded-for"), ["203.0.113.91"]
        )

    async def test_success_body_must_contain_user_object(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("sign-in/email"):
                return _json_response(
                    200,
                    {},
                    headers={
                        "set-cookie": "better-auth.session_token=opaque; Path=/; HttpOnly"
                    },
                )
            # A valid cookie probe must not make a malformed sign-in body valid.
            return _json_response(
                200,
                {"session": {"id": "s"}, "user": {"email": "user@example.test"}},
            )

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.sign_in("09149991680", "not-logged", "192.0.2.1")
        self.assertEqual(raised.exception.kind, AuthFailureKind.INVALID_RESPONSE)
        self.assertEqual(len(requests), 1)

    async def test_session_cookie_pair_is_not_decoded_or_reencoded(self) -> None:
        exact_pair = "better-auth.session_token=A%2FB%2BC%3D%3D"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("sign-in/email"):
                return _json_response(
                    200,
                    {"user": {"id": "u"}, "session": {"id": "s"}},
                    headers=[
                        ("set-cookie", f"{exact_pair}; Path=/; HttpOnly"),
                        ("set-cookie", "unrelated=value; Path=/"),
                    ],
                )
            self.assertEqual(request.headers["cookie"], exact_pair)
            return _json_response(
                200,
                {"session": {"id": "s"}, "user": {"email": "user@example.test"}},
            )

        with _mock_auth_client(handler):
            result = await monorepo_auth.sign_in(
                "09149991680", "not-logged", "192.0.2.1"
            )
        self.assertEqual(result.cookie, exact_pair)

    async def test_missing_or_ambiguous_session_cookie_is_invalid_response(
        self,
    ) -> None:
        headers_cases = (
            [],
            [
                ("set-cookie", "better-auth.session_token=one; Path=/"),
                ("set-cookie", "__Secure-better-auth.session_token=two; Path=/"),
            ],
        )
        for headers in headers_cases:
            with self.subTest(headers=headers):

                def handler(_request: httpx.Request) -> httpx.Response:
                    return _json_response(
                        200,
                        {"user": {"id": "u"}, "session": {"id": "s"}},
                        headers=headers,
                    )

                with _mock_auth_client(handler):
                    with self.assertRaises(MonorepoAuthError) as raised:
                        await monorepo_auth.sign_in(
                            "09149991680", "not-logged", "192.0.2.1"
                        )
                self.assertEqual(
                    raised.exception.kind, AuthFailureKind.INVALID_RESPONSE
                )

    async def test_upstream_sign_in_error_classification(self) -> None:
        cases = (
            (
                400,
                {"code": "INVALID_EMAIL_OR_PASSWORD"},
                {},
                AuthFailureKind.INVALID_CREDENTIALS,
                None,
            ),
            (400, {"code": "INVALID_CLIENT_IP"}, {}, AuthFailureKind.UNAVAILABLE, None),
            (
                400,
                {"code": "SOMETHING_NEW"},
                {},
                AuthFailureKind.INVALID_RESPONSE,
                None,
            ),
            (
                401,
                {"code": "INVALID_EMAIL_OR_PASSWORD"},
                {},
                AuthFailureKind.INVALID_CREDENTIALS,
                None,
            ),
            (403, {"code": "BANNED_USER"}, {}, AuthFailureKind.ACCOUNT_DENIED, None),
            (
                429,
                {"code": "RATE_LIMITED"},
                {"Retry-After": "7"},
                AuthFailureKind.RATE_LIMITED,
                7,
            ),
            (
                503,
                {"code": "RATE_LIMIT_UNAVAILABLE"},
                {},
                AuthFailureKind.UNAVAILABLE,
                None,
            ),
        )
        for status_code, body, headers, expected, retry_after in cases:
            with self.subTest(status=status_code, body=body):

                def handler(_request: httpx.Request) -> httpx.Response:
                    return _json_response(status_code, body, headers=headers)

                with _mock_auth_client(handler):
                    with self.assertRaises(MonorepoAuthError) as raised:
                        await monorepo_auth.sign_in(
                            "09149991680", "not-logged", "192.0.2.1"
                        )
                self.assertEqual(raised.exception.kind, expected)
                self.assertEqual(raised.exception.retry_after_seconds, retry_after)

    async def test_malformed_known_error_and_rate_limit_without_timing_are_invalid_response(
        self,
    ) -> None:
        cases = (
            (401, b"not-json", {}),
            (403, b"not-json", {}),
            (429, json.dumps({"code": "RATE_LIMITED"}).encode(), {}),
            (
                429,
                json.dumps({"code": "RATE_LIMITED"}).encode(),
                {"Retry-After": "tomorrow"},
            ),
        )
        for status_code, body, headers in cases:
            with self.subTest(status=status_code, headers=headers):

                def handler(_request: httpx.Request) -> httpx.Response:
                    return httpx.Response(status_code, content=body, headers=headers)

                with _mock_auth_client(handler):
                    with self.assertRaises(MonorepoAuthError) as raised:
                        await monorepo_auth.sign_in(
                            "09149991680", "not-logged", "192.0.2.1"
                        )
                self.assertEqual(
                    raised.exception.kind, AuthFailureKind.INVALID_RESPONSE
                )

    async def test_transport_failure_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("isolated auth unavailable", request=request)

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.sign_in("09149991680", "not-logged", "192.0.2.1")
        self.assertEqual(raised.exception.kind, AuthFailureKind.UNAVAILABLE)


class SessionContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_session_returns_only_validated_email(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.headers["cookie"], "better-auth.session_token=opaque"
            )
            return _json_response(
                200,
                {"session": {"id": "s"}, "user": {"email": "Learner@Example.test"}},
            )

        with _mock_auth_client(handler):
            result = await monorepo_auth.get_session("better-auth.session_token=opaque")
        self.assertEqual(result.state, SessionState.VALID)
        self.assertEqual(result.email, "Learner@example.test")

    async def test_explicit_invalid_session_shapes_are_not_outages(self) -> None:
        cases = (
            (401, {"error": "Not authenticated"}),
            (200, {}),
            (200, {"session": None, "user": None}),
        )
        for status_code, body in cases:
            with self.subTest(status=status_code, body=body):

                def handler(_request: httpx.Request) -> httpx.Response:
                    return _json_response(status_code, body)

                with _mock_auth_client(handler):
                    result = await monorepo_auth.get_session(
                        "better-auth.session_token=old"
                    )
                self.assertEqual(result.state, SessionState.INVALID)
                self.assertIsNone(result.email)

    async def test_session_outage_and_malformed_success_remain_distinct(self) -> None:
        cases = (
            (503, {"code": "SERVICE_UNAVAILABLE"}, AuthFailureKind.UNAVAILABLE),
            (200, ["not", "an", "object"], AuthFailureKind.INVALID_RESPONSE),
            (
                200,
                {"session": {"id": "s"}, "user": {}},
                AuthFailureKind.INVALID_RESPONSE,
            ),
        )
        for status_code, body, expected in cases:
            with self.subTest(status=status_code, body=body):

                def handler(_request: httpx.Request) -> httpx.Response:
                    return _json_response(status_code, body)

                with _mock_auth_client(handler):
                    with self.assertRaises(MonorepoAuthError) as raised:
                        await monorepo_auth.get_session(
                            "better-auth.session_token=opaque"
                        )
                self.assertEqual(raised.exception.kind, expected)

    async def test_session_transport_failure_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("auth timed out", request=request)

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.get_session("better-auth.session_token=opaque")
        self.assertEqual(raised.exception.kind, AuthFailureKind.UNAVAILABLE)


class LogoutContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_empty_json_for_only_current_cookie_and_confirms_revocation(
        self,
    ) -> None:
        requests: list[httpx.Request] = []
        cookie = "better-auth.session_token=current%2Fopaque"

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.headers["cookie"], cookie)
            if len(requests) == 1:
                return _json_response(
                    200,
                    {"session": {"id": "s"}, "user": {"email": "user@example.test"}},
                )
            if len(requests) == 2:
                self.assertEqual(request.url.path, "/api/auth/sign-out")
                self.assertEqual(request.headers["content-type"], "application/json")
                self.assertEqual(json.loads(request.content), {})
                return _json_response(200, {"success": True})
            return _json_response(401, {"error": "Not authenticated"})

        with _mock_auth_client(handler):
            await monorepo_auth.sign_out(cookie)

        self.assertEqual(
            [request.url.path for request in requests],
            [
                "/api/auth/get-session",
                "/api/auth/sign-out",
                "/api/auth/get-session",
            ],
        )

    async def test_invalid_current_session_never_calls_sign_out(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _json_response(401, {"error": "Not authenticated"})

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.sign_out("better-auth.session_token=old")
        self.assertEqual(raised.exception.kind, AuthFailureKind.INVALID_SESSION)
        self.assertEqual(len(requests), 1)

    async def test_still_authenticated_former_cookie_is_logout_unconfirmed(
        self,
    ) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.path == "/api/auth/sign-out":
                return _json_response(200, {"success": True})
            return _json_response(
                200,
                {"session": {"id": "s"}, "user": {"email": "user@example.test"}},
            )

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.sign_out("better-auth.session_token=current")
        self.assertEqual(raised.exception.kind, AuthFailureKind.LOGOUT_UNCONFIRMED)
        self.assertEqual(calls, 3)

    async def test_malformed_or_rejected_sign_out_is_never_success(self) -> None:
        cases = (
            httpx.Response(200, content=b"not-json"),
            _json_response(200, {"success": False}),
            _json_response(400, {"code": "BAD_REQUEST"}),
        )
        for sign_out_response in cases:
            with self.subTest(response=sign_out_response):

                def handler(request: httpx.Request) -> httpx.Response:
                    if request.url.path == "/api/auth/sign-out":
                        return sign_out_response
                    return _json_response(
                        200,
                        {
                            "session": {"id": "s"},
                            "user": {"email": "user@example.test"},
                        },
                    )

                with _mock_auth_client(handler):
                    with self.assertRaises(MonorepoAuthError) as raised:
                        await monorepo_auth.sign_out(
                            "better-auth.session_token=current"
                        )
                self.assertEqual(
                    raised.exception.kind, AuthFailureKind.LOGOUT_UNCONFIRMED
                )

    async def test_sign_out_transport_failure_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/sign-out":
                raise httpx.ConnectError("sign-out unavailable", request=request)
            return _json_response(
                200,
                {"session": {"id": "s"}, "user": {"email": "user@example.test"}},
            )

        with _mock_auth_client(handler):
            with self.assertRaises(MonorepoAuthError) as raised:
                await monorepo_auth.sign_out("better-auth.session_token=current")
        self.assertEqual(raised.exception.kind, AuthFailureKind.UNAVAILABLE)


class AuthRouteContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_cpf_is_local_422_and_never_calls_upstream_or_db(
        self,
    ) -> None:
        request = _form_request(_login_form("09149991681"))
        upstream = AsyncMock()
        join = AsyncMock()

        with (
            patch.object(auth_routes, "sign_in", upstream),
            patch.object(auth_routes.crud_user, "get_or_create_by_email", join),
        ):
            with self.assertRaises(AuthAPIError) as raised:
                await auth_routes.token(request, db=object())

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.code, AuthErrorCode.INVALID_CPF)
        upstream.assert_not_awaited()
        join.assert_not_awaited()

    async def test_verified_session_email_is_the_only_local_join_key(self) -> None:
        request = _form_request(_login_form("091.499.916-80", "not-logged"))
        authenticated = AuthenticatedSession(
            cookie="better-auth.session_token=opaque",
            email="verified@example.test",
        )
        upstream = AsyncMock(return_value=authenticated)
        join = AsyncMock()

        with (
            patch.object(auth_routes, "sign_in", upstream),
            patch.object(auth_routes.crud_user, "get_or_create_by_email", join),
        ):
            response = await auth_routes.token(request, db=object())

        self.assertEqual(response.access_token, authenticated.cookie)
        upstream.assert_awaited_once_with("09149991680", "not-logged", "198.51.100.10")
        join.assert_awaited_once_with(unittest.mock.ANY, "verified@example.test")
        self.assertNotIn("09149991680", repr(join.await_args))

    async def test_duplicate_fields_or_wrong_content_type_are_local_422(self) -> None:
        requests = (
            _form_request(
                urlencode(
                    [
                        ("username", "09149991680"),
                        ("username", "10323969623"),
                        ("password", "x"),
                    ]
                ).encode()
            ),
            _form_request(
                b'{"username":"09149991680","password":"x"}',
                content_type=b"application/json",
            ),
        )
        for request in requests:
            with self.subTest(content_type=request.headers.get("content-type")):
                upstream = AsyncMock()
                with patch.object(auth_routes, "sign_in", upstream):
                    with self.assertRaises(AuthAPIError) as raised:
                        await auth_routes.token(request, db=object())
                self.assertEqual(raised.exception.status_code, 422)
                self.assertEqual(raised.exception.code, AuthErrorCode.INVALID_REQUEST)
                upstream.assert_not_awaited()

    async def test_route_translates_all_safe_upstream_classes(self) -> None:
        cases = (
            (
                AuthFailureKind.INVALID_CREDENTIALS,
                401,
                AuthErrorCode.INVALID_CREDENTIALS,
            ),
            (AuthFailureKind.ACCOUNT_DENIED, 403, AuthErrorCode.ACCOUNT_DENIED),
            (AuthFailureKind.RATE_LIMITED, 429, AuthErrorCode.RATE_LIMITED),
            (
                AuthFailureKind.INVALID_RESPONSE,
                502,
                AuthErrorCode.AUTH_INVALID_RESPONSE,
            ),
            (AuthFailureKind.UNAVAILABLE, 503, AuthErrorCode.AUTH_UNAVAILABLE),
        )
        for kind, status_code, code in cases:
            with self.subTest(kind=kind):
                error = MonorepoAuthError(
                    kind,
                    retry_after_seconds=7
                    if kind is AuthFailureKind.RATE_LIMITED
                    else None,
                )
                translated = translate_auth_error(error)
                self.assertEqual(translated.status_code, status_code)
                self.assertEqual(translated.code, code)
                if kind is AuthFailureKind.RATE_LIMITED:
                    self.assertEqual(translated.retry_after_seconds, 7)

    async def test_error_handler_emits_stable_top_level_body_and_headers(self) -> None:
        request = _form_request(b"")
        response = await auth_api_error_handler(
            request,
            AuthAPIError(
                429,
                AuthErrorCode.RATE_LIMITED,
                "Muitas tentativas.",
                retry_after_seconds=7,
            ),
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "7")
        self.assertEqual(
            json.loads(response.body),
            {
                "code": "rate_limited",
                "message": "Muitas tentativas.",
                "retry_after_seconds": 7,
            },
        )
        self.assertNotIn("detail", json.loads(response.body))

    async def test_logout_route_returns_204_only_after_core_confirmation(self) -> None:
        revoke = AsyncMock(return_value=None)
        with patch.object(auth_routes, "sign_out", revoke):
            response = await auth_routes.logout("better-auth.session_token=current")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.body, b"")
        revoke.assert_awaited_once_with("better-auth.session_token=current")

        for kind, expected_status in (
            (AuthFailureKind.INVALID_SESSION, 401),
            (AuthFailureKind.LOGOUT_UNCONFIRMED, 502),
            (AuthFailureKind.UNAVAILABLE, 503),
        ):
            with self.subTest(kind=kind):
                revoke = AsyncMock(side_effect=MonorepoAuthError(kind))
                with patch.object(auth_routes, "sign_out", revoke):
                    with self.assertRaises(AuthAPIError) as raised:
                        await auth_routes.logout("better-auth.session_token=current")
                self.assertEqual(raised.exception.status_code, expected_status)

    async def test_logout_route_requires_bearer(self) -> None:
        with self.assertRaises(AuthAPIError) as raised:
            await auth_routes.logout(None)
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.code, AuthErrorCode.AUTH_REQUIRED)


if __name__ == "__main__":
    unittest.main()
