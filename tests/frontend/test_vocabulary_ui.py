from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "shared"))
sys.path.insert(0, str(ROOT / "app" / "frontend"))

import screens.vocabulary as vocabulary_screen  # noqa: E402
import services.media as media_service  # noqa: E402
from controllers.vocabulary_controller import VocabularyController  # noqa: E402
from models.vocabulary import VocabularyLookup  # noqa: E402
from quiz_shared.enums import UserRole  # noqa: E402
from services.api import QuizApiClient  # noqa: E402
from services.exceptions import QuizApiError  # noqa: E402
from state.app_state import AppState  # noqa: E402
from widgets.navbar import app_bar  # noqa: E402

LOOKUP_ID = UUID("00000000-0000-4000-8000-000000000001")


def _lookup() -> VocabularyLookup:
    return VocabularyLookup(
        source_text="bom dia",
        translation="good morning",
        definition="A greeting used in the morning.",
        lookup_id=LOOKUP_ID,
    )


def _authenticated_state() -> AppState:
    state = AppState(token="token-A", email="learner@incluir.test")
    state.current_user = SimpleNamespace(role=UserRole.STUDENT)  # type: ignore[assignment]
    state.auth_session_generation = 7
    return state


def _walk_controls(control: Any):
    seen: set[int] = set()
    pending = [control]
    child_attributes = (
        "content",
        "controls",
        "actions",
        "items",
        "leading",
        "suffix",
        "suffix_icon",
        "title",
    )
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attribute in child_attributes:
            child = getattr(current, attribute, None)
            if isinstance(child, (list, tuple)):
                pending.extend(child)
            elif child is not None and not isinstance(child, (str, int, float, bool)):
                pending.append(child)


def _keyed(control: Any, key: str) -> Any:
    return next(item for item in _walk_controls(control) if item.key == key)


def _text_values(control: Any) -> set[str]:
    return {
        item.value
        for item in _walk_controls(control)
        if isinstance(item, vocabulary_screen.ft.Text) and isinstance(item.value, str)
    }


def _render_screen(
    monkeypatch: pytest.MonkeyPatch,
    state: AppState,
    controller: object,
    values: list[object],
    *,
    setters: list[tuple[str, object]] | None = None,
):
    names = iter(
        [
            "text",
            "result",
            "lookup_status",
            "lookup_message",
            "audio_status",
            "audio_message",
        ]
    )
    hooks = iter(values)
    refs: list[SimpleNamespace] = []

    def use_state(initial):
        name = next(names)
        value = next(hooks)

        def setter(next_value):
            if setters is not None:
                setters.append((name, next_value))

        return value, setter

    def use_ref(initial):
        ref = SimpleNamespace(current=initial)
        refs.append(ref)
        return ref

    effects: list[tuple[object, tuple]] = []
    monkeypatch.setattr(vocabulary_screen, "use_state", use_state)
    monkeypatch.setattr(vocabulary_screen, "use_ref", use_ref)
    monkeypatch.setattr(
        vocabulary_screen,
        "use_effect",
        lambda callback, deps, *cleanup: effects.append((callback, cleanup)),
    )
    page = SimpleNamespace(title="", route="/vocabulario", navigate=lambda route: None)
    monkeypatch.setattr(vocabulary_screen.ft, "context", SimpleNamespace(page=page))
    view = vocabulary_screen.VocabularyScreen.__wrapped__(
        state, controller, SimpleNamespace(state=state)
    )
    return view, refs, effects, page


def test_vocabulary_lookup_model_is_strict_and_typed() -> None:
    result = _lookup()

    assert result.lookup_id == LOOKUP_ID
    with pytest.raises(ValueError):
        VocabularyLookup.model_validate(
            {
                **result.model_dump(),
                "unexpected": "not in the v1.2 contract",
            }
        )


def test_vocabulary_api_uses_lookup_id_only_for_pronunciation() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("/lookup"):
            return httpx.Response(
                200,
                json={
                    "source_text": "bom dia",
                    "translation": "good morning",
                    "definition": "A greeting used in the morning.",
                    "lookup_id": str(LOOKUP_ID),
                },
            )
        return httpx.Response(
            200,
            content=b"ID3\x04\x00\x00pronunciation",
            headers={"content-type": "audio/mpeg"},
        )

    async def scenario():
        api = QuizApiClient()
        await api._client.aclose()
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        lookup = await api.lookup_vocabulary("opaque-token", "bom dia")
        audio = await api.pronounce_vocabulary("opaque-token", str(lookup.lookup_id))
        await api.aclose()
        return lookup, audio

    lookup, audio = asyncio.run(scenario())

    assert lookup.translation == "good morning"
    assert audio.startswith(b"ID3")
    assert requests == [
        ("/api/v1/vocabulary/lookup", {"text": "bom dia"}),
        (
            "/api/v1/vocabulary/pronunciation",
            {"lookup_id": str(LOOKUP_ID)},
        ),
    ]
    assert all("translation" not in body for _, body in requests)


def test_vocabulary_controller_binds_grant_and_results_to_session_generation() -> None:
    async def scenario():
        lookup_started = asyncio.Event()
        lookup_release = asyncio.Event()
        audio_started = asyncio.Event()
        audio_release = asyncio.Event()

        class Api:
            async def lookup_vocabulary(self, token: str, text: str):
                lookup_started.set()
                await lookup_release.wait()
                return _lookup()

            async def pronounce_vocabulary(self, token: str, lookup_id: str):
                audio_started.set()
                await audio_release.wait()
                return b"ID3-old-session"

        state = _authenticated_state()
        controller = VocabularyController(state, Api())  # type: ignore[arg-type]

        stale_lookup = asyncio.create_task(controller.lookup("bom dia"))
        await lookup_started.wait()
        state.set_authenticated_session(
            "token-B",
            SimpleNamespace(email="b@incluir.test", role=UserRole.STUDENT),
        )
        lookup_release.set()
        old_lookup_result = await stale_lookup

        state.vocabulary_lookup_id = str(LOOKUP_ID)
        stale_audio = asyncio.create_task(controller.pronunciation())
        await audio_started.wait()
        state.set_authenticated_session(
            "token-C",
            SimpleNamespace(email="c@incluir.test", role=UserRole.STUDENT),
        )
        audio_release.set()
        old_audio_result = await stale_audio
        return state, old_lookup_result, old_audio_result

    state, old_lookup_result, old_audio_result = asyncio.run(scenario())

    assert old_lookup_result is None
    assert old_audio_result is None
    assert state.token == "token-C"
    assert state.vocabulary_lookup_id is None


def test_vocabulary_controller_installs_current_lookup_grant() -> None:
    class Api:
        async def lookup_vocabulary(self, token: str, text: str):
            assert (token, text) == ("token-A", "bom dia")
            return _lookup()

    state = _authenticated_state()
    result = asyncio.run(
        VocabularyController(state, Api()).lookup("bom dia")  # type: ignore[arg-type]
    )

    assert result == _lookup()
    assert state.vocabulary_lookup_id == str(LOOKUP_ID)


def test_newer_vocabulary_lookup_supersedes_delayed_result() -> None:
    async def scenario():
        first_started = asyncio.Event()
        first_release = asyncio.Event()
        second_started = asyncio.Event()
        second_release = asyncio.Event()
        second_id = UUID("00000000-0000-4000-8000-000000000002")

        class Api:
            async def lookup_vocabulary(self, token: str, text: str):
                if text == "primeiro":
                    first_started.set()
                    await first_release.wait()
                    return _lookup()
                second_started.set()
                await second_release.wait()
                return VocabularyLookup(
                    source_text="segundo",
                    translation="second",
                    definition="Coming after the first.",
                    lookup_id=second_id,
                )

        state = _authenticated_state()
        controller = VocabularyController(state, Api())  # type: ignore[arg-type]
        first = asyncio.create_task(controller.lookup("primeiro"))
        await first_started.wait()
        second = asyncio.create_task(controller.lookup("segundo"))
        await second_started.wait()
        second_release.set()
        second_result = await second
        first_release.set()
        first_result = await first
        return state, first_result, second_result, second_id

    state, first_result, second_result, second_id = asyncio.run(scenario())

    assert first_result is None
    assert second_result is not None
    assert second_result.translation == "second"
    assert state.vocabulary_lookup_id == str(second_id)


def test_vocabulary_initial_tree_is_named_touchable_and_provider_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Controller:
        def __getattr__(self, name: str):
            raise AssertionError(f"provider method called on mount: {name}")

    state = _authenticated_state()
    view, _, effects, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["", None, "idle", "", "idle", ""],
    )

    field = _keyed(view, "vocabulary-input")
    submit = _keyed(view, "vocabulary-submit")
    text = _text_values(view)

    assert field.label == "Palavra ou frase em português"
    assert field.size_constraints.min_height >= 44
    assert submit.content == "Traduzir"
    assert submit.height >= 44
    assert "Vocabulário" in text
    assert "Traduza do português para o inglês e ouça a pronúncia." in text
    assert "Sua tradução aparecerá aqui." in text
    assert len(effects) == 2


def test_vocabulary_lookup_suppresses_duplicate_submit_and_commits_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls: list[str] = []
        setter_values: list[tuple[str, object]] = []
        state = _authenticated_state()

        class Controller:
            def session_snapshot(self):
                return state.token, state.auth_session_generation

            def session_is_current(self, token: str, generation: int) -> bool:
                return (
                    state.token == token
                    and state.auth_session_generation == generation
                )

            async def lookup(self, text: str):
                calls.append(text)
                started.set()
                await release.wait()
                state.vocabulary_lookup_id = str(LOOKUP_ID)
                return _lookup()

        async def reset(page) -> None:
            return None

        monkeypatch.setattr(vocabulary_screen, "reset_audio_source", reset)
        view, _, _, _ = _render_screen(
            monkeypatch,
            state,
            Controller(),
            ["  bom dia  ", None, "idle", "", "idle", ""],
            setters=setter_values,
        )
        submit = _keyed(view, "vocabulary-submit")
        first = asyncio.create_task(submit.on_click(None))
        await started.wait()
        await submit.on_click(None)
        release.set()
        await first
        return calls, setter_values

    calls, setter_values = asyncio.run(scenario())

    assert calls == ["bom dia"]
    assert ("lookup_status", "loading") in setter_values
    assert ("lookup_status", "success") in setter_values
    assert ("result", _lookup()) in setter_values


def test_pronunciation_is_user_initiated_and_replays_cached_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.vocabulary_lookup_id = str(LOOKUP_ID)
    provider_calls: list[str] = []
    plays: list[bytes] = []

    class Controller:
        def session_snapshot(self):
            return state.token, state.auth_session_generation

        def session_is_current(self, token: str, generation: int) -> bool:
            return (
                state.token == token
                and state.auth_session_generation == generation
            )

        async def pronunciation(self):
            provider_calls.append("pronunciation")
            return b"ID3-pronunciation"

    async def play(page, content: bytes) -> None:
        plays.append(content)

    monkeypatch.setattr(vocabulary_screen, "play_audio_bytes", play)
    view, refs, _, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "idle", ""],
    )
    speaker = _keyed(view, "vocabulary-pronunciation")

    assert provider_calls == []
    assert plays == []
    assert speaker.content == "Ouvir pronúncia"
    assert speaker.height >= 44

    asyncio.run(speaker.on_click(None))
    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert plays == [b"ID3-pronunciation"]

    # A second tap is accepted only after the playback completion callback
    # releases the busy guard; the already-fetched bytes are then replayed.
    refs[4].current = False
    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert plays == [b"ID3-pronunciation", b"ID3-pronunciation"]
    assert "Voz gerada por inteligência artificial." in _text_values(view)
    assert "good morning" in _text_values(view)


def test_vocabulary_audio_error_keeps_translation_and_exposes_retryable_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.vocabulary_lookup_id = str(LOOKUP_ID)
    setter_values: list[tuple[str, object]] = []

    class Controller:
        def session_snapshot(self):
            return state.token, state.auth_session_generation

        def session_is_current(self, token: str, generation: int) -> bool:
            return (
                state.token == token
                and state.auth_session_generation == generation
            )

        async def pronunciation(self):
            raise QuizApiError(
                503,
                "provider unavailable",
                code="provider_unavailable",
                message="Vocabulário indisponível no momento.",
            )

    view, _, _, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "idle", ""],
        setters=setter_values,
    )
    asyncio.run(_keyed(view, "vocabulary-pronunciation").on_click(None))

    assert ("audio_status", "error") in setter_values
    assert (
        "audio_message",
        "Vocabulário indisponível no momento.",
    ) in setter_values
    assert "good morning" in _text_values(view)


def test_vocabulary_rate_limit_message_includes_bounded_retry() -> None:
    error = QuizApiError(
        429,
        "rate limited",
        code="rate_limited",
        message="Limite de consultas atingido.",
        retry_after_seconds=42,
    )

    assert vocabulary_screen.vocabulary_error_message(error, "fallback") == (
        "Limite de consultas atingido. Tente novamente em 42s."
    )


def test_generated_audio_helpers_require_bytes_and_reset_to_local_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Audio:
        src: str | bytes = "https://quiz-media.example/question.mp3"

        async def pause(self):
            calls.append("pause")

        async def play(self):
            calls.append("play")

        def update(self):
            calls.append("update")

    audio = Audio()
    monkeypatch.setattr(media_service, "ensure_audio", lambda page: audio)

    with pytest.raises(ValueError):
        asyncio.run(media_service.play_audio_bytes(object(), b""))

    asyncio.run(media_service.play_audio_bytes(object(), b"ID3-audio"))
    assert audio.src == b"ID3-audio"
    assert calls == ["update", "play"]

    asyncio.run(media_service.reset_audio_source(object()))
    assert audio.src == media_service.PLACEHOLDER_SRC
    assert calls == ["update", "play", "pause", "update"]


def test_vocabulary_navigation_is_available_to_student_and_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for role in (UserRole.STUDENT, UserRole.ADMIN):
        state = _authenticated_state()
        state.current_user = SimpleNamespace(role=role)  # type: ignore[assignment]
        routes: list[str] = []
        monkeypatch.setattr(
            vocabulary_screen.ft,
            "context",
            SimpleNamespace(page=SimpleNamespace(navigate=routes.append)),
        )
        bar = app_bar(state, SimpleNamespace(state=state))
        item = _keyed(bar, "account-vocabulary")
        item.on_click(None)
        assert item.height >= 44
        assert item.content == "Vocabulário"
        assert routes == ["/vocabulario"]
