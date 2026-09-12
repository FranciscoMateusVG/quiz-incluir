from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user, get_optional_current_user
from app.core.database import get_db
from app.core.question_types import public_config
from app.crud import question as crud_question
from app.models import Question, QuestionMedia, User, UserRole
from app.schemas.media import MediaRead
from app.schemas.question import QuestionCreate, QuestionRead, QuestionUpdate

router = APIRouter()


async def _to_read(
    db: AsyncSession, question: Question, *, reveal_answers: bool = False
) -> QuestionRead:
    media_result = await db.exec(
        select(QuestionMedia).where(QuestionMedia.question_id == question.id)
    )
    media = [MediaRead.model_validate(m) for m in media_result.all()]
    return QuestionRead(
        id=question.id,
        type=question.type,
        prompt=question.prompt,
        suggested_score=question.suggested_score,
        # The read endpoints are public, so the answer key is withheld unless
        # an admin is asking. Grading and the PDF report read the ORM row
        # directly and are unaffected.
        config=question.config if reveal_answers else public_config(question.config),
        created_at=question.created_at,
        media=media,
    )


def _may_reveal_answers(user: User | None) -> bool:
    return user is not None and user.role == UserRole.ADMIN


@router.get("", response_model=list[QuestionRead])
async def list_questions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[QuestionRead]:
    result = await db.exec(
        select(Question).order_by(Question.created_at).offset(skip).limit(limit)
    )
    questions = list(result.all())
    reveal = _may_reveal_answers(current_user)
    return [await _to_read(db, q, reveal_answers=reveal) for q in questions]


@router.post("", response_model=QuestionRead, status_code=status.HTTP_201_CREATED)
async def create_question(
    question_in: QuestionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuestionRead:
    question = await crud_question.create(db, question_in)
    return await _to_read(db, question, reveal_answers=True)


@router.get("/{question_id}", response_model=QuestionRead)
async def read_question(
    question_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> QuestionRead:
    question = await crud_question.get_or_404(db, question_id)
    return await _to_read(
        db, question, reveal_answers=_may_reveal_answers(current_user)
    )


@router.patch("/{question_id}", response_model=QuestionRead)
async def update_question(
    question_id: UUID,
    question_in: QuestionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuestionRead:
    question = await crud_question.get_or_404(db, question_id)
    question = await crud_question.update(db, question, question_in)
    return await _to_read(db, question, reveal_answers=True)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await crud_question.remove(db, question_id)
