"""Typed client for the existing Programa Incluir BetterAuth service.

The opaque session cookie is never decoded locally. Every accepted login,
protected request and logout is decided by the same Hono/BetterAuth service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from email_validator import EmailNotValidError, validate_email

from app.core.config import settings


AUTH_HOP_TIMEOUT_SECONDS = 4.0
AUTH_FLOW_TIMEOUT_SECONDS = 12.0
_CREDENTIAL_REJECTION_CODES = {"INVALID_EMAIL_OR_PASSWORD"}


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
    email: str | None = None


@dataclass(frozen=True)
class AuthenticatedSession:
    cookie: str
    email: str


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
    parsed = int(value)
    return parsed if parsed > 0 else None


def _extract_session_cookie(response: httpx.Response) -> str:
    session_cookies: list[str] = []
    for header in response.headers.get_list("set-cookie"):
        pair = header.split(";", 1)[0]
        name, separator, value = pair.partition("=")
        if (
            not separator
            or not name
            or not value
            or name != name.strip()
            or "\r" in pair
            or "\n" in pair
        ):
            continue
        if name.lower().endswith("session_token"):
            session_cookies.append(pair)
    if len(session_cookies) != 1:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    return session_cookies[0]


def _validated_email(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    try:
        # ``.test`` is deliberately used by the isolated real-BetterAuth
        # fixtures. test_environment relaxes only reserved test-domain policy;
        # syntax validation remains active.
        return validate_email(
            value, check_deliverability=False, test_environment=True
        ).normalized
    except EmailNotValidError as exc:
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE) from exc


async def _session_check(client: httpx.AsyncClient, cookie: str) -> SessionCheck:
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

    session = data.get("session")
    user = data.get("user")
    if not session:
        return SessionCheck(SessionState.INVALID)
    if not isinstance(session, dict) or not isinstance(user, dict):
        raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
    return SessionCheck(SessionState.VALID, _validated_email(user.get("email")))


async def sign_in(cpf: str, password: str, client_ip: str) -> AuthenticatedSession:
    """Sign in by CPF, verify the new cookie and return only verified identity."""

    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=AUTH_HOP_TIMEOUT_SECONDS) as client:
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
                session = await _session_check(client, cookie)
                if session.state is not SessionState.VALID or session.email is None:
                    raise MonorepoAuthError(AuthFailureKind.INVALID_RESPONSE)
                return AuthenticatedSession(cookie=cookie, email=session.email)
    except TimeoutError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc


async def get_session(cookie: str) -> SessionCheck:
    """Return a typed session verdict; outages never become invalid sessions."""

    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=AUTH_HOP_TIMEOUT_SECONDS) as client:
                return await _session_check(client, cookie)
    except TimeoutError as exc:
        raise MonorepoAuthError(AuthFailureKind.UNAVAILABLE) from exc


async def sign_out(cookie: str) -> None:
    """Revoke only this cookie and prove that it no longer authenticates."""

    try:
        async with asyncio.timeout(AUTH_FLOW_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=AUTH_HOP_TIMEOUT_SECONDS) as client:
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
