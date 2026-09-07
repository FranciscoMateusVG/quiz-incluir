from typing import Annotated

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
                            "description": "CPF: 11 ASCII digits or NNN.NNN.NNN-NN",
                        },
                        "password": {"type": "string", "format": "password"},
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

    try:
        form = await request.form()
    except Exception as exc:
        raise _invalid_request("Formulário inválido.") from exc

    usernames = form.getlist("username")
    passwords = form.getlist("password")
    if (
        len(usernames) != 1
        or len(passwords) != 1
        or not isinstance(usernames[0], str)
        or not isinstance(passwords[0], str)
        or passwords[0] == ""
    ):
        raise _invalid_request()

    cpf = normalize_cpf(usernames[0])
    if cpf is None:
        raise AuthAPIError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            AuthErrorCode.INVALID_CPF,
            "CPF inválido.",
        )

    client_ip = resolve_auth_request_client_ip(request, settings.trusted_proxy_networks)
    try:
        authenticated = await sign_in(cpf, passwords[0], client_ip)
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
