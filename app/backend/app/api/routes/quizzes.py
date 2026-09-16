from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud import quiz as crud_quiz
from app.models import Question, Quiz, QuizMedia, QuizQuestion, User
from app.schemas.media import QuizMediaRead
from app.schemas.quiz import (
    QuizCreate,
    QuizQuestionLink,
    QuizQuestionLinkCreate,
    QuizRead,
    QuizUpdate,
)

router = APIRouter()


async def _to_read(db: AsyncSession, quiz: Quiz) -> QuizRead:
    question_ids = await crud_quiz.get_question_ids(db, quiz.id)
    media_result = await db.exec(
        select(QuizMedia).where(QuizMedia.quiz_id == quiz.id).order_by(QuizMedia.position)
    )
    media = [QuizMediaRead.model_validate(m) for m in media_result.all()]
    return QuizRead(
        id=quiz.id,
        title=quiz.title,
        description=quiz.description,
        category=quiz.category,
        level=quiz.level,
        course_level=quiz.course_level,
        unit=quiz.unit,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        question_ids=question_ids,
        media=media,
    )


@router.get("", response_model=list[QuizRead])
async def list_quizzes(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> list[QuizRead]:
    result = await db.exec(select(Quiz).order_by(Quiz.created_at).offset(skip).limit(limit))
    quizzes = list(result.all())
    return [await _to_read(db, q) for q in quizzes]


@router.post("", response_model=QuizRead, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    quiz_in: QuizCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizRead:
    quiz = await crud_quiz.create(db, quiz_in)
    return await _to_read(db, quiz)


@router.get("/{quiz_id}", response_model=QuizRead)
async def read_quiz(
    quiz_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QuizRead:
    quiz = await crud_quiz.get_or_404(db, quiz_id)
    return await _to_read(db, quiz)


@router.patch("/{quiz_id}", response_model=QuizRead)
async def update_quiz(
    quiz_id: UUID,
    quiz_in: QuizUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizRead:
    quiz = await crud_quiz.get_or_404(db, quiz_id)
    quiz = await crud_quiz.update(db, quiz, quiz_in)
    return await _to_read(db, quiz)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    quiz_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await crud_quiz.remove(db, quiz_id)


@router.post(
    "/{quiz_id}/questions",
    response_model=QuizQuestionLink,
    status_code=status.HTTP_201_CREATED,
)
async def add_question_to_quiz(
    quiz_id: UUID,
    link_in: QuizQuestionLinkCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuizQuestion:
    return await crud_quiz.link_question(db, quiz_id, link_in.question_id, link_in.position)


@router.delete("/{quiz_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_question_from_quiz(
    quiz_id: UUID,
    question_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await crud_quiz.unlink_question(db, quiz_id, question_id)


@router.get("/{quiz_id}/questions", response_model=list[QuizQuestionLink])
async def list_quiz_questions(
    quiz_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[QuizQuestion]:
    result = await db.exec(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    return list(result.all())
