"""Authentication flow: log in, fetch the profile, navigate to the picker."""

from __future__ import annotations

from services.api import QuizApiClient
from state.app_state import AppState


class AuthController:
    def __init__(self, state: AppState, api: QuizApiClient):
        self.state = state
        self.api = api

    async def login(self, cpf: str, password: str) -> None:
        token = await self.api.login(cpf, password)
        user = await self.api.me(token.access_token)
        self.state.token = token.access_token
        self.state.email = user.email
        self.state.current_user = user
        self.state.auth_notice = ""

    async def logout(self) -> bool:
        """Clear local state always; report whether server revocation was proven."""
        token = self.state.token
        confirmed = False
        try:
            if token is not None:
                await self.api.logout(token)
                confirmed = True
        except Exception:
            confirmed = False
        finally:
            self.state.clear_session()

        if not confirmed:
            self.state.auth_notice = (
                "Você saiu do Quiz, mas não foi possível confirmar o "
                "encerramento da sessão no servidor."
            )
        return confirmed
