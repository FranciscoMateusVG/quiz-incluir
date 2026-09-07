from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.monorepo_auth import VerifiedIdentityEmail
from app.crud.base import CRUDBase
from app.models import CourseLevel, User, UserRole
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        result = await db.exec(select(User).where(User.email == email))
        return result.first()

    async def get_or_create_from_verified_email(
        self, db: AsyncSession, email: VerifiedIdentityEmail
    ) -> User:
        """Mirror a verified monorepo identity into a local shadow ``User`` row.

        Only called after the monorepo has already confirmed the email is a
        real, authenticated user — this never grants access on its own.
        """
        existing = await self.get_by_email(db, email)
        if existing is not None:
            return existing
        user = User(
            email=str(email),
            level=CourseLevel.B1,
            role=UserRole.STUDENT,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


user = CRUDUser(User)
