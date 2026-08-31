from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.grading import normalize_score, normalized_max_score
from app.core.pdf_report import build_attempt_report
from app.crud import attempt as crud_attempt
from app.models import QuizAttempt, User
from app.schemas.answer import AnswerRead, AnswerSubmit
from app.schemas.attempt import AttemptRead, AttemptStart

router = APIRouter()


async def _to_read(db: AsyncSession, attempt: QuizAttempt) -> AttemptRead:
    raw_max = await crud_attempt.get_max_score(db, attempt.quiz_id)
    return AttemptRead(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        user_id=attempt.user_id,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        score=normalize_score(attempt.score, raw_max),
        max_score=normalized_max_score(raw_max),
    )


@router.post("", response_model=AttemptRead, status_code=status.HTTP_201_CREATED)
async def start_attempt(
    start_in: AttemptStart,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttemptRead:
    attempt = await crud_attempt.start(db, current_user, start_in.quiz_id)
    return await _to_read(db, attempt)


@router.get("", response_model=list[AttemptRead])
async def list_attempts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[AttemptRead]:
    result = await db.exec(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == current_user.id)
        .order_by(QuizAttempt.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    attempts = list(result.all())
    return [await _to_read(db, a) for a in attempts]


@router.get("/{attempt_id}", response_model=AttemptRead)
async def read_attempt(
    attempt_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttemptRead:
    attempt = await crud_attempt.get_or_404(db, attempt_id)
    if attempt.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to view this attempt",
        )
    return await _to_read(db, attempt)


@router.post("/{attempt_id}/answers", response_model=AnswerRead)
async def submit_answer(
    attempt_id: UUID,
    answer_in: AnswerSubmit,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    attempt = await crud_attempt.get_or_404(db, attempt_id)
    if attempt.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to answer this attempt",
        )
    if attempt.finished_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attempt already finished",
        )
    return await crud_attempt.submit_answer(db, attempt, answer_in)


@router.post("/{attempt_id}/finish", response_model=AttemptRead)
async def finish_attempt(
    attempt_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttemptRead:
    attempt = await crud_attempt.get_or_404(db, attempt_id)
    if attempt.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to finish this attempt",
        )
    attempt = await crud_attempt.finish(db, attempt)
    return await _to_read(db, attempt)


@router.get("/{attempt_id}/report.pdf")
async def download_attempt_report(
    attempt_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    attempt = await crud_attempt.get_or_404(db, attempt_id)
    if attempt.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to view this attempt",
        )
    quiz, rows = await crud_attempt.get_report_rows(db, attempt)
    max_score = await crud_attempt.get_max_score(db, attempt.quiz_id)
    pdf_bytes = build_attempt_report(quiz, attempt, max_score, rows)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="quiz-report-{attempt_id}.pdf"'
        },
    )
