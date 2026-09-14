"""Stable, non-leaking HTTP errors for shared authentication failures."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.monorepo_auth import AuthFailureKind, MonorepoAuthError
from quiz_shared.schemas import AuthErrorCode, AuthErrorResponse


class AuthAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: AuthErrorCode,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


_AUTH_FAILURES: dict[AuthFailureKind, tuple[int, AuthErrorCode, str]] = {
    AuthFailureKind.INVALID_CREDENTIALS: (
        401,
        AuthErrorCode.INVALID_CREDENTIALS,
        "CPF ou senha inválidos.",
    ),
    AuthFailureKind.ACCOUNT_DENIED: (
        403,
        AuthErrorCode.ACCOUNT_DENIED,
        "Acesso não permitido.",
    ),
    AuthFailureKind.RATE_LIMITED: (
        429,
        AuthErrorCode.RATE_LIMITED,
        "Muitas tentativas. Tente novamente em instantes.",
    ),
    AuthFailureKind.INVALID_SESSION: (
        401,
        AuthErrorCode.AUTH_REQUIRED,
        "Autenticação necessária.",
    ),
    AuthFailureKind.UNAVAILABLE: (
        503,
        AuthErrorCode.AUTH_UNAVAILABLE,
        "Não foi possível entrar agora. Tente novamente.",
    ),
    AuthFailureKind.INVALID_RESPONSE: (
        502,
        AuthErrorCode.AUTH_INVALID_RESPONSE,
        "Não foi possível confirmar a autenticação.",
    ),
    AuthFailureKind.LOGOUT_UNCONFIRMED: (
        502,
        AuthErrorCode.LOGOUT_UNCONFIRMED,
        "Não foi possível confirmar a saída no servidor.",
    ),
}


def translate_auth_error(exc: MonorepoAuthError) -> AuthAPIError:
    status_code, code, message = _AUTH_FAILURES[exc.kind]
    return AuthAPIError(
        status_code,
        code,
        message,
        retry_after_seconds=exc.retry_after_seconds,
    )


async def auth_api_error_handler(_request: Request, exc: AuthAPIError) -> JSONResponse:
    body = AuthErrorResponse(
        code=exc.code,
        message=exc.message,
        retry_after_seconds=exc.retry_after_seconds,
    ).model_dump(mode="json", exclude_none=True)
    headers: dict[str, str] = {}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if exc.status_code == 429 and exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)
