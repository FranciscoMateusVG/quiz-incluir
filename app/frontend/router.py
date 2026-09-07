"""Declarative routing: matches the page URL to a screen component.

Used with ``page.render_views``; ``manage_views=True`` renders each matched
route as a ``ft.View`` so the browser/system back button works.
"""

from __future__ import annotations

from flet import Route, Router, component

from controllers.admin_controller import AdminController
from controllers.auth_controller import AuthController
from controllers.quiz_controller import QuizController
from controllers.vocabulary_controller import VocabularyController
from screens.admin_grades import AdminGradesScreen
from screens.admin_quiz_list import AdminQuizListScreen
from screens.login import LoginScreen
from screens.not_found import NotFoundScreen
from screens.picker import QuizPickerScreen
from screens.question import QuestionScreen
from screens.results import ResultsScreen
from screens.vocabulary import VocabularyScreen
from state.app_state import AppState
from widgets.auth_guard import AuthGuard


def make_app(
    state: AppState,
    auth: AuthController,
    quiz: QuizController,
    admin: AdminController,
    vocabulary: VocabularyController,
) -> component:
    """Build the root component for the current session."""

    @component
    def _login():
        return LoginScreen(auth)

    @component
    def _picker():
        return AuthGuard(state, auth, lambda: QuizPickerScreen(state, quiz, auth))

    @component
    def _question():
        return AuthGuard(state, auth, lambda: QuestionScreen(state, quiz))

    @component
    def _results():
        return AuthGuard(state, auth, lambda: ResultsScreen(state, quiz))

    @component
    def _vocabulary():
        return AuthGuard(
            state,
            auth,
            lambda: VocabularyScreen(state, vocabulary, auth),
        )

    @component
    def _admin_quizzes():
        return AuthGuard(
            state,
            auth,
            lambda: AdminQuizListScreen(state, admin, auth),
            admin_only=True,
        )

    @component
    def _admin_grades():
        return AuthGuard(
            state,
            auth,
            lambda: AdminGradesScreen(state, admin, auth),
            admin_only=True,
        )

    @component
    def App():
        return Router(
            [
                Route(index=True, component=_login),
                Route(path="quizzes", component=_picker),
                Route(path="quiz/:index", component=_question),
                Route(path="results", component=_results),
                Route(path="vocabulario", component=_vocabulary),
                Route(path="admin/grades", component=_admin_quizzes),
                Route(path="admin/grades/:quiz_id", component=_admin_grades),
            ],
            not_found=NotFoundScreen,
            manage_views=True,
        )

    return App
