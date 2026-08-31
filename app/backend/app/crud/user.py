from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.crud.base import CRUDBase
from app.models import User
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        result = await db.exec(select(User).where(User.email == email))
        return result.first()

    async def get_or_create_by_email(self, db: AsyncSession, email: str) -> User:
        """Mirror a verified monorepo identity into a local shadow ``User`` row.

        Only called after the monorepo has already confirmed the email is a
        real, authenticated user — this never grants access on its own.
        """
        existing = await self.get_by_email(db, email)
        if existing is not None:
            return existing
        try:
            return await self.create(db, UserCreate(email=email))
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Please enter a valid email address",
            )


user = CRUDUser(User)
