from typing import Annotated, Optional

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_errors import AuthAPIError, translate_auth_error
from app.core.config import settings
from app.core.database import get_db
from app.core.monorepo_auth import (
    MonorepoAuthError,
    SessionState,
    get_session,
)
from app.crud import user as crud_user
from app.models import User, UserRole
from quiz_shared.schemas import AuthErrorCode


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token",
    auto_error=False,
)


def _auth_required() -> AuthAPIError:
    return AuthAPIError(
        status.HTTP_401_UNAUTHORIZED,
        AuthErrorCode.AUTH_REQUIRED,
        "Autenticação necessária.",
    )


async def _verified_email(token: str) -> str | None:
    try:
        session = await get_session(token)
    except MonorepoAuthError as exc:
        raise translate_auth_error(exc) from exc
    if session.state is SessionState.INVALID:
        return None
    # A VALID state without an email cannot be constructed by the typed client.
    return session.email


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise _auth_required()

    email = await _verified_email(token)
    if email is None:
        raise _auth_required()
    return await crud_user.get_or_create_from_verified_email(db, email)


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.ADMIN:
        # Authorization failures are not authentication failures and retain the
        # existing route contract.
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
) -> Optional[User]:
    if not token:
        return None

    email = await _verified_email(token)
    if email is None:
        return None
    return await crud_user.get_or_create_from_verified_email(db, email)
