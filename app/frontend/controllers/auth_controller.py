"""Authentication flow: log in, fetch the profile, navigate to the picker."""

from __future__ import annotations

from services.api import QuizApiClient
from state.app_state import AppState


class AuthController:
    def __init__(self, state: AppState, api: QuizApiClient):
        self.state = state
        self.api = api

    async def login(self, email: str, password: str) -> None:
        token = await self.api.login(email, password)
        user = await self.api.me(token.access_token)
        self.state.token = token.access_token
        self.state.email = user.email
        self.state.current_user = user

    def logout(self) -> None:
        self.state.token = None
        self.state.email = ""
        self.state.current_user = None