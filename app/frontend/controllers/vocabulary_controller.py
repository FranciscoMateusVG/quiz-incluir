"""Session-bound vocabulary lookup and pronunciation workflow."""

from __future__ import annotations

from models.vocabulary import VocabularyLookup
from services.api import QuizApiClient
from state.app_state import AppState


class VocabularyController:
    def __init__(self, state: AppState, api: QuizApiClient):
        self.state = state
        self.api = api
        self._lookup_generation = 0

    def session_snapshot(self) -> tuple[str, int]:
        token = self.state.token
        if token is None:
            raise RuntimeError("Authentication is required.")
        return token, self.state.auth_session_generation

    def session_is_current(self, token: str, generation: int) -> bool:
        return (
            self.state.token == token
            and self.state.auth_session_generation == generation
        )

    async def lookup(self, text: str) -> VocabularyLookup | None:
        """Look up text and install only the current session's audio grant."""
        token, generation = self.session_snapshot()
        self._lookup_generation += 1
        lookup_generation = self._lookup_generation
        self.state.vocabulary_lookup_id = None
        try:
            result = await self.api.lookup_vocabulary(token, text)
        except Exception:
            if (
                not self.session_is_current(token, generation)
                or lookup_generation != self._lookup_generation
            ):
                return None
            raise
        if (
            not self.session_is_current(token, generation)
            or lookup_generation != self._lookup_generation
        ):
            return None
        self.state.vocabulary_lookup_id = str(result.lookup_id)
        return result

    async def pronunciation(self) -> bytes | None:
        """Fetch audio for the server-owned lookup grant, never client text."""
        token, generation = self.session_snapshot()
        lookup_generation = self._lookup_generation
        lookup_id = self.state.vocabulary_lookup_id
        if lookup_id is None:
            raise RuntimeError("A current vocabulary lookup is required.")
        try:
            content = await self.api.pronounce_vocabulary(token, lookup_id)
        except Exception:
            if (
                not self.session_is_current(token, generation)
                or lookup_generation != self._lookup_generation
            ):
                return None
            raise
        if (
            not self.session_is_current(token, generation)
            or lookup_generation != self._lookup_generation
            or self.state.vocabulary_lookup_id != lookup_id
        ):
            return None
        return content
