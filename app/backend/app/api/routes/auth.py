from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.monorepo_auth import MonorepoAuthError, sign_in
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
    email = form_data.username.strip().lower()
    if not email or not form_data.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email and password are required",
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        session_token = await sign_in(email, form_data.password, client_ip)
    except MonorepoAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await crud_user.get_or_create_by_email(db, email)
    return Token(access_token=session_token)


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
