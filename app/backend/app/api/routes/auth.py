from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, oauth2_scheme
from app.core.database import get_db
from app.core.monorepo_auth import MonorepoAuthError, get_session, sign_in, sign_out
from app.crud import user as crud_user
from app.models import User
from app.schemas.token import Token
from app.schemas.user import UserRead

router = APIRouter()


@router.post("/token", response_model=Token)
async def token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    # `username` carries a CPF here, not an email — every login screen in the
    # monorepo authenticates by CPF (see monorepo_auth.sign_in's docstring).
    # No `.lower()`: meaningless for a CPF, unlike the email this field used
    # to hold.
    cpf = form_data.username.strip()
    if not cpf or not form_data.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cpf and password are required",
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        session_token = await sign_in(cpf, form_data.password, client_ip)
    except MonorepoAuthError as exc:
        headers = {"WWW-Authenticate": "Bearer"}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail, headers=headers
        )

    # The local shadow `users` row is keyed by email, but the field the caller
    # just authenticated with is a CPF — fetch the real email hono-app has on
    # file for this session rather than trying to derive one from the CPF.
    session = await get_session(session_token)
    email = (session or {}).get("user", {}).get("email") if session else None
    if not email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable",
        )

    await crud_user.get_or_create_by_email(db, email)
    return Token(access_token=session_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session_token: Annotated[str | None, Depends(oauth2_scheme)],
) -> None:
    """Revoke the session server-side, best-effort.

    Deliberately doesn't depend on `get_current_user`: an already-expired or
    already-revoked token should still report success here — the caller's
    goal is "make sure this can't be used again," which is trivially true if
    it already can't be used.
    """
    if session_token:
        await sign_out(session_token)


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
