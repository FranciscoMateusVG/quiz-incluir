from typing import Annotated
from urllib.parse import parse_qsl
import re

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_errors import AuthAPIError, translate_auth_error
from app.api.deps import get_current_user
from app.core.client_ip import resolve_auth_request_client_ip
from app.core.config import settings
from app.core.cpf import normalize_cpf
from app.core.database import get_db
from app.core.monorepo_auth import MonorepoAuthError, sign_in, sign_out
from app.crud import user as crud_user
from app.models import User
from app.schemas.token import Token
from app.schemas.user import UserRead
from quiz_shared.schemas import AuthErrorCode, AuthErrorResponse


router = APIRouter()
logout_bearer = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token", auto_error=False
)

MAX_AUTH_FORM_BYTES = 2048
MAX_CPF_INPUT_CHARS = 64
MAX_PASSWORD_CHARS = 128
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")

_ERROR_RESPONSES = {
    401: {"model": AuthErrorResponse, "description": "Credentials or session rejected"},
    403: {"model": AuthErrorResponse, "description": "Account denied"},
    422: {"model": AuthErrorResponse, "description": "Invalid CPF or request"},
    429: {"model": AuthErrorResponse, "description": "Upstream sign-in rate limit"},
    502: {"model": AuthErrorResponse, "description": "Invalid upstream response"},
    503: {"model": AuthErrorResponse, "description": "Authentication unavailable"},
}
_FORM_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "required": ["username", "password"],
                    "properties": {
                        "username": {
                            "type": "string",
                            "maxLength": MAX_CPF_INPUT_CHARS,
                            "description": "CPF: 11 ASCII digits or NNN.NNN.NNN-NN",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "minLength": 1,
                            "maxLength": MAX_PASSWORD_CHARS,
                        },
                    },
                }
            }
        },
    }
}


def _invalid_request(message: str = "CPF e senha são obrigatórios.") -> AuthAPIError:
    return AuthAPIError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        AuthErrorCode.INVALID_REQUEST,
        message,
    )


async def _read_limited_form_body(request: Request) -> bytes:
    content_lengths = request.headers.getlist("content-length")
    if len(content_lengths) > 1:
        raise _invalid_request("Formulário inválido.")
    if content_lengths:
        try:
            declared_length = int(content_lengths[0])
        except ValueError as exc:
            raise _invalid_request("Formulário inválido.") from exc
        if declared_length < 0 or declared_length > MAX_AUTH_FORM_BYTES:
            raise _invalid_request("Formulário muito grande.")

    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_AUTH_FORM_BYTES:
                raise _invalid_request("Formulário muito grande.")
            body.extend(chunk)
    except AuthAPIError:
        raise
    except Exception as exc:
        raise _invalid_request("Formulário inválido.") from exc
    return bytes(body)


def _parse_login_form(body: bytes) -> tuple[str, str]:
    try:
        encoded = body.decode("ascii")
        if _INVALID_PERCENT_ESCAPE.search(encoded):
            raise ValueError("invalid percent escape")
        fields = parse_qsl(
            encoded,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeError, ValueError) as exc:
        raise _invalid_request("Formulário inválido.") from exc

    if len(fields) != 2 or {name for name, _value in fields} != {
        "username",
        "password",
    }:
        raise _invalid_request()
    values = dict(fields)
    username = values["username"]
    password = values["password"]
    if (
        not username
        or len(username) > MAX_CPF_INPUT_CHARS
        or not password
        or len(password) > MAX_PASSWORD_CHARS
    ):
        raise _invalid_request()
    return username, password


@router.post(
    "/token",
    response_model=Token,
    responses=_ERROR_RESPONSES,
    openapi_extra=_FORM_OPENAPI,
)
async def token(request: Request, db: AsyncSession = Depends(get_db)) -> Token:
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if content_type != "application/x-www-form-urlencoded":
        raise _invalid_request("Envie CPF e senha como formulário.")

    username, password = _parse_login_form(await _read_limited_form_body(request))

    cpf = normalize_cpf(username)
    if cpf is None:
        raise AuthAPIError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            AuthErrorCode.INVALID_CPF,
            "CPF inválido.",
        )

    client_ip = resolve_auth_request_client_ip(request, settings.trusted_proxy_networks)
    try:
        authenticated = await sign_in(cpf, password, client_ip)
    except MonorepoAuthError as exc:
        raise translate_auth_error(exc) from exc

    # The local identity/role join is derived only from the separately verified
    # BetterAuth get-session payload returned by sign_in().
    await crud_user.get_or_create_by_email(db, authenticated.email)
    return Token(access_token=authenticated.cookie)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        401: _ERROR_RESPONSES[401],
        502: _ERROR_RESPONSES[502],
        503: _ERROR_RESPONSES[503],
    },
)
async def logout(
    token: Annotated[str | None, Depends(logout_bearer)],
) -> Response:
    if not token:
        raise AuthAPIError(
            status.HTTP_401_UNAUTHORIZED,
            AuthErrorCode.AUTH_REQUIRED,
            "Autenticação necessária.",
        )
    try:
        await sign_out(token)
    except MonorepoAuthError as exc:
        raise translate_auth_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead, responses=_ERROR_RESPONSES)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
