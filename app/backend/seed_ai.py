"""Seed the database with AI-generated questions.

Reads the cached questions+quiz metadata produced by
``ai/question_generation.py`` (``ai/questions_cache.json`` by
default) and stores them as a ``Quiz``/``QuizMedia``/``Question`` rows. The
original ``seed.py`` demo data is left untouched.

Usage:
    ../.venv/bin/python seed_ai.py              # seed from existing cache
    ../.venv/bin/python seed_ai.py --generate   # (re)generate the cache first
    ../.venv/bin/python seed_ai.py --reset      # wipe questions/quiz links first
"""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlmodel import func, select

from app.core.database import async_session_maker, init_db
from db_models import (
    Answer,
    LanguageLevel,
    MediaType,
    Question,
    QuestionMedia,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizCategory,
    QuizMedia,
    QuizQuestion,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = REPO_ROOT / "ai" / "questions_cache.json"

sys.path.insert(0, str(REPO_ROOT))


async def clear_quiz_data(session) -> None:
    for model in (Answer, QuizAttempt, QuestionMedia, QuizMedia, QuizQuestion, Question, Quiz):
        await session.exec(delete(model))
    await session.commit()


def build_config(data: dict) -> dict:
    qtype = data["type"]
    if qtype == "multiple_choice":
        return {
            "options": data["choices"],
            "correct_index": data["correct"],
            "explanations": data["explanations"],
        }
    if qtype == "multiple_selection":
        return {
            "options": data["choices"],
            "correct_indices": data["correct"],
            "explanations": data["explanations"],
        }
    if qtype == "true_false":
        return {"answer": data["correct"]}
    if qtype == "short_text":
        return {"accepted_answers": [data["correct"]]}
    raise ValueError(f"Unknown question type: {qtype!r}")


async def seed() -> None:
    await init_db()

    if "--generate" in sys.argv:
        from ai.question_generation import ACTIVE_SOURCE, generate_questions, write_cache

        questions = generate_questions(ACTIVE_SOURCE)
        write_cache(ACTIVE_SOURCE, questions, CACHE_FILE)
        print(f"Generated {len(questions)} questions -> {CACHE_FILE}")

    if not CACHE_FILE.exists():
        raise SystemExit(
            f"Cache not found: {CACHE_FILE}. Run `python seed_ai.py --generate` first."
        )

    payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    quiz_data = payload["quiz"]
    questions_data = payload["questions"]

    async with async_session_maker() as session:
        if "--reset" in sys.argv:
            await clear_quiz_data(session)

        existing = (
            await session.exec(
                select(func.count(Question.id)).where(
                    Question.prompt.in_([q["prompt"] for q in questions_data])
                )
            )
        ).one()
        if existing > 0:
            print(
                "Database already contains these questions. Use --reset to reseed."
            )
            return

        rows = [
            Question(
                type=QuestionType(data["type"]),
                prompt=data["prompt"],
                suggested_score=data["suggested_score"],
                config=build_config(data),
            )
            for data in questions_data
        ]
        session.add_all(rows)
        await session.flush()

        quiz = Quiz(
            title=quiz_data["title"],
            description=quiz_data["description"],
            category=QuizCategory(quiz_data["category"]),
            level=LanguageLevel(quiz_data["level"]),
        )
        session.add(quiz)
        await session.flush()

        session.add(
            QuizMedia(
                quiz_id=quiz.id,
                type=MediaType(quiz_data["media_type"]),
                url=quiz_data["media_url"],
                caption=quiz_data["media_caption"],
                position=0,
            )
        )

        for position, question in enumerate(rows):
            session.add(
                QuizQuestion(
                    quiz_id=quiz.id,
                    question_id=question.id,
                    position=position,
                )
            )

        await session.commit()
        print(
            f"Seeded: {len(rows)} questions in quiz '{quiz.title}' "
            f"(category={quiz.category.value}, level={quiz.level.value})"
        )


if __name__ == "__main__":
    asyncio.run(seed())
