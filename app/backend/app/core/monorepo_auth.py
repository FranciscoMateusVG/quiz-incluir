"""Thin client for the Programa Incluir monorepo's auth API (hono-app / BetterAuth).

BetterAuth issues an opaque, DB-backed session cookie — not a JWT — and the
monorepo deliberately doesn't expose a bearer-token plugin (see
``apps/hono-app/src/auth/auth.ts``). This module never decodes or verifies a
session locally: it relays the raw cookie value to the monorepo's own
endpoints and trusts whatever it says, the same way the monorepo's own
consumer apps (e.g. ``apps/coordenador``) validate sessions.
"""

from __future__ import annotations

import httpx

from app.core.config import settings


class MonorepoAuthError(Exception):
    """Raised when the monorepo rejects a sign-in attempt."""


async def sign_in(email: str, password: str, client_ip: str) -> str:
    """Sign in against the monorepo and return the opaque session cookie string.

    ``client_ip`` is forwarded as ``X-Forwarded-For``: the monorepo's sign-in
    bridge rejects requests with no resolvable client IP (its rate limiter
    keys on it) regardless of environment, so a real end-user IP must be
    relayed through here rather than the quiz backend's own address.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{settings.MONOREPO_AUTH_URL}/api/auth/sign-in/email",
                json={"email": email, "password": password},
                headers={"X-Forwarded-For": client_ip},
            )
        except httpx.HTTPError as exc:
            raise MonorepoAuthError("Could not reach the authentication service") from exc

    if response.status_code >= 400:
        raise MonorepoAuthError("Invalid credentials")

    cookie_header = "; ".join(
        cookie.split(";", 1)[0]
        for cookie in response.headers.get_list("set-cookie")
    )
    if not cookie_header:
        raise MonorepoAuthError("Authentication service did not return a session")
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
