"""Typed client for the existing Programa Incluir BetterAuth service.

The opaque session cookie is never decoded locally. Every accepted login,
protected request and logout is decided by the same Hono/BetterAuth service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, NewType

import httpx
from email_validator import EmailNotValidError, validate_email
from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from quiz_shared.schemas import CanonicalIdentityEmail


AUTH_HOP_TIMEOUT_SECONDS = 4.0
AUTH_FLOW_TIMEOUT_SECONDS = 12.0
MAX_SESSION_COOKIE_PAIR_BYTES = 4096
MAX_RETRY_AFTER_SECONDS = 10
_CREDENTIAL_REJECTION_CODES = {"INVALID_EMAIL_OR_PASSWORD"}
_SESSION_COOKIE_NAMES = {
    "better-auth.session_token",
    "__Secure-better-auth.session_token",
}
VerifiedIdentityEmail = NewType("VerifiedIdentityEmail", str)
_canonical_identity_adapter = TypeAdapter(CanonicalIdentityEmail)


class AuthFailureKind(StrEnum):
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_DENIED = "account_denied"
    RATE_LIMITED = "rate_limited"
    INVALID_SESSION = "invalid_session"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    LOGOUT_UNCONFIRMED = "logout_unconfirmed"


class MonorepoAuthError(Exception):
    """A classified upstream outcome safe for translation at the API edge."""

    def __init__(
        self, kind: AuthFailureKind, *, retry_after_seconds: int | None = None
    ) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


class SessionState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class SessionCheck:
    state: SessionState
    email: VerifiedIdentityEmail | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, SessionState):
            raise ValueError("invalid session state")
        if self.state is SessionState.VALID:
            if not isinstance(self.email, str) or not self.email:
                raise ValueError("valid session requires an email")
        elif self.email is not None:
            raise ValueError("invalid session cannot carry an email")


@dataclass(frozen=True)
class AuthenticatedSession:
    cookie: str
    email: VerifiedIdentityEmail


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    significant = value.lstrip("0")
    if not significant:
        return None
    if len(significant) > len(str(MAX_RETRY_AFTER_SECONDS)):
        return MAX_RETRY_AFTER_SECONDS
    return min(int(significant), MAX_RETRY_AFTER_SECONDS)


def _new_auth_client() -> httpx.AsyncClient:
    """Build the private auth client without ambient proxy or redirect trust."""

    return httpx.AsyncClient(
        timeout=AUTH_HOP_TIMEOUT_SECONDS,
        trust_env=False,
        follow_redirects=False,
    )


def _validate_session_cookie_pair(
    cookie: object, *, failure_kind: AuthFailureKind
) -> str:
    """Validate one opaque BetterAuth cookie pair without transforming it."""

    if not isinstance(cookie, str) or not cookie:
        raise MonorepoAuthError(failure_kind)
    try:
        encoded = cookie.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MonorepoAuthError(failure_kind) from exc
    if (
        len(encoded) > MAX_SESSION_COOKIE_PAIR_BYTES
        or ";" in cookie
        or "," in cookie
    ):
        raise MonorepoAuthError(failure_kind)

    name, separator, value = cookie.partition("=")
    if separator != "=" or name not in _SESSION_COOKIE_NAMES or not value:
        raise MonorepoAuthError(failure_kind)

    # RFC 6265 cookie-octet: %x21 / %x23-2B / %x2D-3A / %x3C-5B / %x5D-7E.
    # This excludes whitespace, controls, DQUOTE, comma, semicolon, backslash,
    # and non-ASCII input while preserving the opaque pair byte-for-byte.
    if any(
        not (
            code == 0x21
            or 0x23 <= code <= 0x2B
            or 0x2D <= code <= 0x3A
            or 0x3C <= code <= 0x5B
            or 0x5D <= code <= 0x7E
        )
        for code in map(ord, value)
    ):
        raise MonorepoAuthError(failure_kind)
    return cookie


def _extract_session_cookie(response: httpx.Response) -> str:
    session_cookies: list[str] = []
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        name = pair.partition("=")[0]
        if name in _SESSION_COOKIE_NAMES:
            session_cookies.append(
                _validate_session_cookie_pair(
                    pair, failure_kind=AuthFailureKind.INVALID_RESPONSE
                )
            )
    if len(session_cookies) != 1:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    return session_cookies[0]


def _validated_email(value: object) -> VerifiedIdentityEmail:
    if not isinstance(value, str) or not value.strip():
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    try:
        # ``.test`` is deliberately used by the isolated real-BetterAuth
        # fixtures. test_environment relaxes only reserved test-domain policy;
        # syntax validation remains active.
        normalized = validate_email(
            value, check_deliverability=False, test_environment=True
        ).normalized
        safe_identity = _canonical_identity_adapter.validate_python(normalized)
        return VerifiedIdentityEmail(safe_identity)
    except (EmailNotValidError, ValidationError) as exc:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE) from exc


async def _session_check(
    client: httpx.AsyncClient,
    cookie: str,
    *,
    cookie_failure_kind: AuthFailureKind = AuthFailureKind.INVALID_SESSION,
) -> SessionCheck:
    cookie = _validate_session_cookie_pair(cookie, failure_kind=cookie_failure_kind)
    try:
        response = await client.get(
            f"{settings.MONOREPO_AUTH_URL}/api/auth/get-session",
            headers={"Cookie": cookie},
        )
    except httpx.RequestError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc

    if response.status_code == 401:
        error = _safe_json(response)
        if error == {"error": "Not authenticated"}:
            return SessionCheck(SessionState.INVALID)
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    if response.status_code >= 500:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE)
    if response.status_code != 200:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)

    try:
        data = response.json()
    except ValueError as exc:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE) from exc
    if data is None:
        return SessionCheck(SessionState.INVALID)
    if not isinstance(data, dict):
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)

    if "session" not in data or data["session"] is None:
        return SessionCheck(SessionState.INVALID)
    session = data["session"]
    user = data.get("user")
    if not isinstance(session, dict) or not isinstance(user, dict):
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    session_id = session.get("id")
    user_id = user.get("id")
    if (
        not isinstance(session_id, str)
        or not session_id.strip()
        or not isinstance(user_id, str)
        or not user_id.strip()
    ):
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    return SessionCheck(SessionState.VALID, _validated_email(user.get("email")))


async def sign_in(cpf: str, password: str, client_ip: str) -> AuthenticatedSession:
    """Sign in by CPF, verify the new cookie and return only verified identity."""

    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with _new_auth_client() as client:
                try:
                    response = await client.post(
                        f"{settings.MONOREPO_AUTH_URL}/api/auth/sign-in/email",
                        json={"cpf": cpf, "password": password},
                        headers={"X-Forwarded-For": client_ip},
                    )
                except httpx.RequestError as exc:
                    raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc

                error_body = _safe_json(response)
                error_code = error_body.get("code") if error_body is not None else None
                if response.status_code in {400, 401}:
                    if error_code in _CREDENTIAL_REJECTION_CODES:
                        raise MonorepoAuthError(AuthFailureKind.INVALID_CREDENTIALS)
                    if error_code == "INVALID_CLIENT_IP":
                        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE)
                    raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
                if response.status_code == 403:
                    if error_code == "BANNED_USER":
                        raise MonorepoAuthError(AuthFailureKind.ACCOUNT_DENIED)
                    raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
                if response.status_code == 429:
                    retry_after = _retry_after_seconds(response)
                    if error_code != "RATE_LIMITED" or retry_after is None:
                        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
                    raise MonorepoAuthError(
                        AuthFailureKind.RATE_LIMITED,
                        retry_after_seconds=retry_after,
                    )
                if response.status_code >= 500:
                    raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE)
                if (
                    response.status_code != 200
                    or error_body is None
                    or not isinstance(error_body.get("user"), dict)
                ):
                    raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)

                cookie = _extract_session_cookie(response)
                session = await _session_check(
                    client,
                    cookie,
                    cookie_failure_kind=AuthFailureKind.INVALID_RESPONSE,
                )
                if session.state is not SessionState.VALID or session.email is None:
                    raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
                return AuthenticatedSession(cookie=cookie, email=session.email)
    except TimeoutError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc


async def get_session(cookie: str) -> SessionCheck:
    """Return a typed session verdict; outages never become invalid sessions."""

    cookie = _validate_session_cookie_pair(
        cookie, failure_kind=AuthFailureKind.INVALID_SESSION
    )
    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with _new_auth_client() as client:
                return await _session_check(client, cookie)
    except TimeoutError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc


async def sign_out(cookie: str) -> None:
    """Revoke only this cookie and prove that it no longer authenticates."""

    cookie = _validate_session_cookie_pair(
        cookie, failure_kind=AuthFailureKind.INVALID_SESSION
    )
    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with _new_auth_client() as client:
                current = await _session_check(client, cookie)
                if current.state is SessionState.INVALID:
                    raise MonorepoAuthError(AuthFailureKind.INVALID_SESSION)

                try:
                    response = await client.post(
                        f"{settings.MONOREPO_AUTH_URL}/api/auth/sign-out",
                        headers={"Cookie": cookie},
                        json={},
                    )
                except httpx.RequestError as exc:
                    raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc

                if response.status_code >= 500:
                    raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE)
                if response.status_code != 200:
                    raise MonorepoAuthError(AuthFailureKind.LOGOUT_UNCONFIRMED)
                data = _safe_json(response)
                if data is None or data.get("success") is not True:
                    raise MonorepoAuthError(AuthFailureKind.LOGOUT_UNCONFIRMED)

                former = await _session_check(client, cookie)
                if former.state is not SessionState.INVALID:
                    raise MonorepoAuthError(AuthFailureKind.LOGOUT_UNCONFIRMED)
    except TimeoutError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc
