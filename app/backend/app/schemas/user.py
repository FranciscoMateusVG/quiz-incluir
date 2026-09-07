from pydantic import ConfigDict, EmailStr, Field
from sqlmodel import SQLModel

from app.models import CourseLevel
from quiz_shared.schemas import UserRead

__all__ = ["UserBase", "UserCreate", "UserRead", "UserUpdate", "UserLevelUpdate"]


class UserBase(SQLModel):
    email: EmailStr
    level: CourseLevel = CourseLevel.B1


class UserCreate(UserBase):
    pass


class UserUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    level: CourseLevel | None = None


class UserLevelUpdate(SQLModel):
    level: CourseLevel = Field(description="New course level for the user")
