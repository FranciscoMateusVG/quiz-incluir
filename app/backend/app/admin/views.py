"""SQLAdmin ``ModelView``s for every table in the app."""

from __future__ import annotations

from sqladmin import ModelView

from app.models import (
    Answer,
    Question,
    QuestionMedia,
    Quiz,
    QuizAttempt,
    QuizMedia,
    QuizQuestion,
    User,
)


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    column_list = [User.id, User.email, User.level, User.role, User.created_at]
    column_searchable_list = [User.email]
    column_sortable_list = [User.email, User.level, User.role, User.created_at]


class QuizAdmin(ModelView, model=Quiz):
    name = "Quiz"
    name_plural = "Quizzes"
    icon = "fa-solid fa-list-check"

    column_list = [Quiz.id, Quiz.title, Quiz.category, Quiz.level, Quiz.created_at]
    column_searchable_list = [Quiz.title]
    column_sortable_list = [Quiz.title, Quiz.category, Quiz.level, Quiz.created_at]
    form_excluded_columns = [Quiz.questions, Quiz.attempts, Quiz.media]


class QuestionAdmin(ModelView, model=Question):
    name = "Question"
    name_plural = "Questions"
    icon = "fa-solid fa-circle-question"

    column_list = [Question.id, Question.type, Question.prompt, Question.suggested_score]
    column_searchable_list = [Question.prompt]
    column_sortable_list = [Question.type, Question.suggested_score]
    column_formatters = {
        Question.prompt: lambda m, a: (m.prompt[:80] + "…") if len(m.prompt) > 80 else m.prompt
    }
    form_excluded_columns = [Question.media, Question.quizzes, Question.answers]


class QuizQuestionAdmin(ModelView, model=QuizQuestion):
    name = "Quiz ↔ Question link"
    name_plural = "Quiz ↔ Question links"
    icon = "fa-solid fa-link"

    column_list = [QuizQuestion.quiz, QuizQuestion.question, QuizQuestion.position]
    form_columns = [QuizQuestion.quiz, QuizQuestion.question, QuizQuestion.position]
    column_sortable_list = [QuizQuestion.position]
    form_ajax_refs = {"question": {"fields": ["prompt"], "order_by": "prompt"}}


class QuizMediaAdmin(ModelView, model=QuizMedia):
    name = "Quiz Media"
    name_plural = "Quiz Media"
    icon = "fa-solid fa-photo-film"

    column_list = [
        QuizMedia.id,
        QuizMedia.quiz,
        QuizMedia.type,
        QuizMedia.url,
        QuizMedia.position,
    ]
    column_sortable_list = [QuizMedia.type, QuizMedia.position]


class QuestionMediaAdmin(ModelView, model=QuestionMedia):
    name = "Question Media"
    name_plural = "Question Media"
    icon = "fa-solid fa-image"

    column_list = [
        QuestionMedia.id,
        QuestionMedia.question,
        QuestionMedia.type,
        QuestionMedia.url,
        QuestionMedia.position,
    ]
    column_sortable_list = [QuestionMedia.type, QuestionMedia.position]
    form_ajax_refs = {"question": {"fields": ["prompt"], "order_by": "prompt"}}


class QuizAttemptAdmin(ModelView, model=QuizAttempt):
    name = "Quiz Attempt"
    name_plural = "Quiz Attempts"
    icon = "fa-solid fa-clock"

    column_list = [
        QuizAttempt.id,
        QuizAttempt.user,
        QuizAttempt.quiz,
        QuizAttempt.started_at,
        QuizAttempt.finished_at,
        QuizAttempt.score,
    ]
    column_sortable_list = [QuizAttempt.started_at, QuizAttempt.finished_at, QuizAttempt.score]
    form_excluded_columns = [QuizAttempt.answers]


class AnswerAdmin(ModelView, model=Answer):
    name = "Answer"
    name_plural = "Answers"
    icon = "fa-solid fa-pen"

    column_list = [
        Answer.id,
        Answer.attempt,
        Answer.question,
        Answer.is_correct,
        Answer.points_awarded,
        Answer.answered_at,
    ]
    column_sortable_list = [Answer.is_correct, Answer.points_awarded, Answer.answered_at]
    form_ajax_refs = {"question": {"fields": ["prompt"], "order_by": "prompt"}}


ALL_VIEWS = [
    UserAdmin,
    QuizAdmin,
    QuestionAdmin,
    QuizQuestionAdmin,
    QuizMediaAdmin,
    QuestionMediaAdmin,
    QuizAttemptAdmin,
    AnswerAdmin,
]
