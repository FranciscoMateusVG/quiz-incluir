from fastapi import APIRouter

from app.api.routes import (
    admin,
    answers,
    attempts,
    auth,
    media,
    questions,
    quiz_media,
    quizzes,
    users,
)

api_router = APIRouter()
api_router.include_router(auth, prefix="/auth", tags=["auth"])
api_router.include_router(admin, prefix="/admin", tags=["admin"])
api_router.include_router(users, prefix="/users", tags=["users"])
api_router.include_router(questions, prefix="/questions", tags=["questions"])
api_router.include_router(quizzes, prefix="/quizzes", tags=["quizzes"])
api_router.include_router(media, prefix="/media", tags=["media"])
api_router.include_router(quiz_media, prefix="/quiz-media", tags=["quiz-media"])
api_router.include_router(attempts, prefix="/attempts", tags=["attempts"])
api_router.include_router(answers, prefix="/answers", tags=["answers"])
