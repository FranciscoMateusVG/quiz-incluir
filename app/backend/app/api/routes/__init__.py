from app.api.routes.admin import router as admin
from app.api.routes.answers import router as answers
from app.api.routes.attempts import router as attempts
from app.api.routes.auth import router as auth
from app.api.routes.media import router as media
from app.api.routes.questions import router as questions
from app.api.routes.quiz_media import router as quiz_media
from app.api.routes.quizzes import router as quizzes
from app.api.routes.users import router as users
from app.api.routes.vocabulary import router as vocabulary

__all__ = [
    "admin",
    "answers",
    "attempts",
    "auth",
    "media",
    "questions",
    "quiz_media",
    "quizzes",
    "users",
    "vocabulary",
]
