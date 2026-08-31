from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.analytics_db import get_analytics_connection
from app.core.database import get_db
from app.core.grading import normalize_score, normalized_max_score
from app.crud import attempt as crud_attempt
from app.models import CourseLevel, User
from app.schemas.admin import AdminAttemptRow, QuestionStatRow

router = APIRouter()


def _query_attempts(quiz_id: str, level: str | None) -> list[dict]:
    con = get_analytics_connection()
    try:
        where = "qa.quiz_id::text = ?"
        params: list[str] = [quiz_id]
        if level is not None:
            where += " AND u.level::text = ?"
            params.append(level)
        rows = con.execute(
            f"""
            SELECT
                qa.id AS attempt_id,
                qa.user_id AS user_id,
                u.email AS email,
                u.level::text AS level,
                qa.score AS score,
                qa.finished_at AS finished_at
            FROM pg.quiz_attempts qa
            JOIN pg.users u ON u.id = qa.user_id
            WHERE {where}
            ORDER BY u.email
            """,
            params,
        ).fetchall()
        columns = [d[0] for d in con.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()


def _query_question_stats(quiz_id: str, level: str | None) -> list[dict]:
    con = get_analytics_connection()
    try:
        finished_where = "qa.quiz_id::text = ? AND qa.finished_at IS NOT NULL"
        params: list[str] = [quiz_id]
        if level is not None:
            finished_where += " AND u.level::text = ?"
            params.append(level)
        params.append(quiz_id)
        rows = con.execute(
            f"""
            WITH finished_attempts AS (
                SELECT qa.id AS attempt_id
                FROM pg.quiz_attempts qa
                JOIN pg.users u ON u.id = qa.user_id
                WHERE {finished_where}
            ),
            quiz_questions AS (
                SELECT question_id FROM pg.quiz_questions WHERE quiz_id::text = ?
            )
            SELECT
                q.id AS question_id,
                q.prompt AS prompt,
                COUNT(*) FILTER (WHERE a.is_correct = true) AS correct_count,
                COUNT(*) FILTER (WHERE a.is_correct = false) AS incorrect_count,
                COUNT(*) FILTER (WHERE a.id IS NULL) AS unanswered_count
            FROM quiz_questions qq
            JOIN pg.questions q ON q.id = qq.question_id
            CROSS JOIN finished_attempts fa
            LEFT JOIN pg.answers a
                ON a.attempt_id = fa.attempt_id AND a.question_id = qq.question_id
            GROUP BY q.id, q.prompt
            ORDER BY q.id
            """,
            params,
        ).fetchall()
        columns = [d[0] for d in con.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()


@router.get("/quizzes/{quiz_id}/attempts", response_model=list[AdminAttemptRow])
async def admin_list_quiz_attempts(
    quiz_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    level: CourseLevel | None = None,
) -> list[AdminAttemptRow]:
    raw_max = await crud_attempt.get_max_score(db, quiz_id)
    rows = await anyio.to_thread.run_sync(
        _query_attempts, str(quiz_id), level.value if level else None
    )
    return [
        AdminAttemptRow(
            attempt_id=row["attempt_id"],
            user_id=row["user_id"],
            email=row["email"],
            level=row["level"],
            score=normalize_score(row["score"], raw_max),
            max_score=normalized_max_score(raw_max),
            finished=row["finished_at"] is not None,
            finished_at=row["finished_at"],
        )
        for row in rows
    ]


@router.get("/quizzes/{quiz_id}/question-stats", response_model=list[QuestionStatRow])
async def admin_question_stats(
    quiz_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    level: CourseLevel | None = None,
) -> list[QuestionStatRow]:
    rows = await anyio.to_thread.run_sync(
        _query_question_stats, str(quiz_id), level.value if level else None
    )
    return [
        QuestionStatRow(
            question_id=row["question_id"],
            prompt=row["prompt"],
            correct_count=row["correct_count"],
            incorrect_count=row["incorrect_count"],
            unanswered_count=row["unanswered_count"],
        )
        for row in rows
    ]
