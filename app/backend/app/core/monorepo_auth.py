"""Thin client for the Programa Incluir monorepo's auth API (hono-app / BetterAuth).

BetterAuth issues an opaque, DB-backed session cookie — not a JWT — and the
monorepo deliberately doesn't expose a bearer-token plugin (see
``apps/hono-app/src/auth/auth.ts``). This module never decodes or verifies a
session locally: it relays the raw cookie value to the monorepo's own
endpoints and trusts whatever it says, the same way the monorepo's own
consumer apps (e.g. ``apps/coordenador``) validate sessions.

Sign-in uses CPF, not email: every login screen in the monorepo (including
its own public-facing app) authenticates by CPF, and ``POST
/api/auth/sign-in/email`` accepts ``{cpf, password}`` directly — the CPF to
email lookup happens inside hono-app's own route handler
(``apps/hono-app/src/http/app.ts``), so no separate lookup is needed here.
"""

from __future__ import annotations

import re

import httpx

from app.core.config import settings


class MonorepoAuthError(Exception):
    """Raised when the monorepo rejects a sign-in attempt.

    Carries enough of hono-app's own response to let the caller react
    correctly instead of treating every failure as a wrong password — in
    particular, distinguishing "try again" (429, with ``retry_after``) and
    "the service is down" (503) from genuinely invalid credentials (401)
    matters for what the login screen should tell the user.
    """

    def __init__(self, status_code: int, detail: str, retry_after: int | None = None):
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


def _digits_only(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


async def sign_in(cpf: str, password: str, client_ip: str) -> str:
    """Sign in against the monorepo and return the opaque session cookie string.

    ``client_ip`` is forwarded as ``X-Forwarded-For``: the monorepo's sign-in
    bridge rejects requests with no resolvable client IP (its rate limiter
    keys on it) regardless of environment, so a real end-user IP must be
    relayed through here rather than the quiz backend's own address.

    ``cpf`` is sent as digits only, with no other client-side validation —
    matching how the monorepo's own standalone apps (``apps/secretaria``,
    ``apps/coordenador``, ...) pass it straight through and let hono-app be
    the sole authority on whether it's well-formed or known.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{settings.MONOREPO_AUTH_URL}/api/auth/sign-in/email",
                json={"cpf": _digits_only(cpf), "password": password},
                headers={"X-Forwarded-For": client_ip},
            )
        except httpx.HTTPError as exc:
            raise MonorepoAuthError(
                503, "Could not reach the authentication service"
            ) from exc

    if response.status_code == 429:
        retry_after = None
        header = response.headers.get("retry-after")
        if header is not None:
            try:
                retry_after = int(header)
            except ValueError:
                retry_after = None
        raise MonorepoAuthError(429, "Too many sign-in attempts", retry_after)

    if response.status_code == 503:
        raise MonorepoAuthError(503, "Sign-in is temporarily unavailable")

    if response.status_code == 400:
        raise MonorepoAuthError(400, "Invalid sign-in request")

    if response.status_code >= 400:
        # Covers 401 (wrong CPF/password) and anything else unexpected —
        # treated as invalid credentials rather than leaking hono-app
        # internals for cases this module doesn't specifically know about.
        raise MonorepoAuthError(401, "Invalid credentials")

    cookie_header = "; ".join(
        cookie.split(";", 1)[0]
        for cookie in response.headers.get_list("set-cookie")
    )
    if not cookie_header:
        raise MonorepoAuthError(503, "Authentication service did not return a session")
    return cookie_header


async def get_session(cookie_value: str) -> dict | None:
    """Validate an opaque session cookie against the monorepo. Returns the
    ``{session, user}`` payload, or ``None`` if the session isn't valid."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{settings.MONOREPO_AUTH_URL}/api/auth/get-session",
                headers={"Cookie": cookie_value},
            )
        except httpx.HTTPError:
            return None

    if response.status_code != 200:
        return None

    data = response.json()
    if not data or not data.get("session") or not data.get("user"):
        return None
    return data


async def sign_out(cookie_value: str) -> None:
    """Best-effort session revocation. Mirrors ``apps/frontend``'s own
    logout, which actually invalidates the session server-side rather than
    just discarding it client-side (the standalone apps have no logout at
    all and rely on the 7-day expiry).

    Never raises: the caller's contract is "make sure this token can't be
    reused," which is best-effort regardless of whether the monorepo is
    reachable right now — a network hiccup here must not block sign-out.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # BetterAuth rejects any POST with no body/Content-Type as
            # 415 Unsupported Media Type before it even looks at the
            # session — a bodiless request here silently "succeeded" (no
            # exception) while never actually revoking anything.
            await client.post(
                f"{settings.MONOREPO_AUTH_URL}/api/auth/sign-out",
                headers={"Cookie": cookie_value, "Content-Type": "application/json"},
                content=b"{}",
            )
        except httpx.HTTPError:
            pass
