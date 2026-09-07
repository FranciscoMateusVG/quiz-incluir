"""Authentication flow: log in, fetch the profile, navigate to the picker."""

from __future__ import annotations

import asyncio

from services.exceptions import QuizApiError
from services.api import QuizApiClient
from state.app_state import AppState

AUTH_UNAVAILABLE_MESSAGE = "Não foi possível verificar sua sessão. Tente novamente."


class AuthController:
    def __init__(self, state: AppState, api: QuizApiClient):
        self.state = state
        self.api = api
        self._validation_lock = asyncio.Lock()
        self._validation_generation = 0

    async def login(self, cpf: str, password: str) -> bool:
        generation = self.state.auth_session_generation
        active_token = self.state.token
        try:
            token = await self.api.login(cpf, password)
            if (
                self.state.auth_session_generation != generation
                or self.state.token != active_token
            ):
                return False
            user = await self.api.me(token.access_token)
        except Exception:
            if (
                self.state.auth_session_generation != generation
                or self.state.token != active_token
            ):
                return False
            raise
        if (
            self.state.auth_session_generation != generation
            or self.state.token != active_token
        ):
            return False
        self.state.set_authenticated_session(token.access_token, user)
        return True

    def mark_validated_route(self, route: str) -> None:
        """Trust the route against the fresh /users/me result from login."""
        self.state.auth_validation_route = route
        self.state.auth_validation_message = ""
        self.state.auth_validation_status = "valid"

    def invalidate_validation(self) -> None:
        """Block protected rendering until a fresh authoritative session check."""
        self._validation_generation += 1
        self.state.invalidate_auth_validation()

    async def revalidate(self, route: str, *, force: bool = False) -> str:
        """Validate the retained token before rendering one protected route.

        The generation and token checks prevent a late /users/me result from
        restoring content after logout, disconnect, or a newer route check.
        """
        async with self._validation_lock:
            token = self.state.token
            session_generation = self.state.auth_session_generation
            if token is None or self.state.current_user is None:
                return "invalid"
            if (
                not force
                and self.state.auth_validation_status == "valid"
                and self.state.auth_validation_route == route
            ):
                return "valid"

            self._validation_generation += 1
            generation = self._validation_generation
            self.state.auth_validation_status = "checking"
            self.state.auth_validation_route = route
            self.state.auth_validation_message = ""

            try:
                user = await self.api.me(token)
            except QuizApiError as error:
                # QuizApiClient invokes the global invalid-session transition
                # exactly once for this proven outcome. Do not overwrite it.
                if error.status_code == 401 and error.code == "auth_required":
                    return "invalid" if self.state.token is None else "stale"
                if (
                    generation == self._validation_generation
                    and self.state.token == token
                    and self.state.auth_session_generation == session_generation
                    and self.state.auth_validation_route == route
                ):
                    self.state.auth_validation_message = AUTH_UNAVAILABLE_MESSAGE
                    self.state.auth_validation_status = "unavailable"
                return "unavailable"
            except Exception:
                if (
                    generation == self._validation_generation
                    and self.state.token == token
                    and self.state.auth_session_generation == session_generation
                    and self.state.auth_validation_route == route
                ):
                    self.state.auth_validation_message = AUTH_UNAVAILABLE_MESSAGE
                    self.state.auth_validation_status = "unavailable"
                return "unavailable"

            if (
                generation != self._validation_generation
                or self.state.token != token
                or self.state.auth_session_generation != session_generation
                or self.state.auth_validation_route != route
            ):
                return "stale"

            # Status becomes valid only after the authoritative user and role.
            self.state.current_user = user
            self.state.email = user.email
            self.state.auth_validation_route = route
            self.state.auth_validation_message = ""
            self.state.auth_validation_status = "valid"
            return "valid"

    async def logout(self) -> bool:
        """Clear local state always; report whether server revocation was proven."""
        token = self.state.token
        generation = self.state.auth_session_generation
        confirmed = False
        try:
            if token is not None:
                await self.api.logout(token)
                confirmed = True
        except Exception:
            confirmed = False
        finally:
            if (
                self.state.auth_session_generation == generation
                and self.state.token == token
            ):
                self._validation_generation += 1
                self.state.clear_session()

        if (
            not confirmed
            and self.state.auth_session_generation == generation + 1
            and self.state.token is None
        ):
            self.state.auth_notice = (
                "Você saiu do Quiz, mas não foi possível confirmar o "
                "encerramento da sessão no servidor."
            )
        return confirmed
