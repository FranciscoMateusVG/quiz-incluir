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
from widgets.auth_guard import AuthGuard, protected_route_key  # noqa: E402
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


def test_vocabulary_results_are_named_accessible_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.vocabulary_lookup_id = str(LOOKUP_ID)
    view, _, _, _ = _render_screen(
        monkeypatch,
        state,
        SimpleNamespace(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "idle", ""],
    )

    translation = _keyed(view, "vocabulary-translation")
    definition = _keyed(view, "vocabulary-definition")

    assert translation.semantics_label == "Tradução em inglês: good morning"
    assert definition.semantics_label == (
        "Definição em inglês: A greeting used in the morning."
    )
    assert translation.selectable is not True
    assert definition.selectable is not True


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
    prepared: list[bytes] = []
    plays: list[float] = []
    refs_holder: list[SimpleNamespace] = []
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
            provider_calls.append("pronunciation")
            return b"ID3-pronunciation"

    async def prepare(page, content: bytes, *, is_current) -> bool:
        prepared.append(content)
        return is_current()

    async def play(page, *, timeout: float) -> None:
        plays.append(timeout)
        refs_holder[6].current.set()

    monkeypatch.setattr(vocabulary_screen, "prepare_audio_bytes", prepare)
    monkeypatch.setattr(vocabulary_screen, "play_prepared_audio", play)
    view, refs, _, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "idle", ""],
        setters=setter_values,
    )
    refs_holder.extend(refs)
    speaker = _keyed(view, "vocabulary-pronunciation")

    assert provider_calls == []
    assert prepared == []
    assert plays == []
    assert speaker.content == "Ouvir pronúncia"
    assert speaker.height >= 44

    asyncio.run(speaker.on_click(None))
    assert provider_calls == ["pronunciation"]
    assert prepared == [b"ID3-pronunciation"]
    assert plays == []
    assert refs[4].current is False
    assert ("audio_status", "ready") in setter_values
    assert (
        "audio_message",
        "Áudio pronto. Toque novamente para ouvir.",
    ) in setter_values

    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert prepared == [b"ID3-pronunciation"]
    assert plays == [vocabulary_screen.GENERATED_AUDIO_TIMEOUT]

    # A second tap is accepted only after the playback completion callback
    # releases the busy guard; the already-fetched bytes are then replayed.
    refs[4].current = False
    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert prepared == [b"ID3-pronunciation"]
    assert plays == [
        vocabulary_screen.GENERATED_AUDIO_TIMEOUT,
        vocabulary_screen.GENERATED_AUDIO_TIMEOUT,
    ]
    assert "Voz gerada por inteligência artificial." in _text_values(view)
    assert "good morning" in _text_values(view)


def test_vocabulary_play_timeout_reenables_retry_without_refetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.vocabulary_lookup_id = str(LOOKUP_ID)
    provider_calls: list[str] = []
    setter_values: list[tuple[str, object]] = []
    refs_holder: list[SimpleNamespace] = []
    play_calls = 0

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

    async def prepare(page, content: bytes, *, is_current) -> bool:
        return is_current()

    async def timeout(page, *, timeout: float) -> None:
        nonlocal play_calls
        play_calls += 1
        if play_calls == 1:
            raise TimeoutError("browser did not answer")
        refs_holder[6].current.set()

    monkeypatch.setattr(vocabulary_screen, "prepare_audio_bytes", prepare)
    monkeypatch.setattr(vocabulary_screen, "play_prepared_audio", timeout)
    view, refs, _, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "idle", ""],
        setters=setter_values,
    )
    refs_holder.extend(refs)
    speaker = _keyed(view, "vocabulary-pronunciation")

    asyncio.run(speaker.on_click(None))
    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert refs[4].current is False
    assert ("audio_status", "error") in setter_values
    assert any(
        name == "audio_message" and "indisponível" in str(value).lower()
        for name, value in setter_values
    )

    asyncio.run(speaker.on_click(None))

    assert provider_calls == ["pronunciation"]
    assert play_calls == 2


def test_vocabulary_audio_state_events_are_the_only_playback_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setter_values: list[tuple[str, object]] = []

    class Audio:
        on_state_change = None
        src = media_service.PLACEHOLDER_SRC

        def update(self):
            return None

    audio = Audio()

    async def reset(page) -> None:
        return None

    monkeypatch.setattr(vocabulary_screen, "ensure_audio", lambda page: audio)
    monkeypatch.setattr(vocabulary_screen, "reset_audio_source", reset)
    view, refs, effects, _ = _render_screen(
        monkeypatch,
        _authenticated_state(),
        SimpleNamespace(),
        ["", None, "idle", "", "idle", ""],
        setters=setter_values,
    )

    async def scenario() -> None:
        effects[1][0]()
        await asyncio.sleep(0)
        refs[4].current = True
        refs[5].current = True
        refs[6].current = asyncio.Event()

        audio.on_state_change(
            SimpleNamespace(state=vocabulary_screen.AudioState.PLAYING)
        )
        assert refs[6].current.is_set()
        assert refs[4].current is True

        audio.on_state_change(
            SimpleNamespace(state=vocabulary_screen.AudioState.COMPLETED)
        )
        assert refs[4].current is False

        refs[4].current = True
        refs[5].current = True
        audio.on_state_change(
            SimpleNamespace(state=vocabulary_screen.AudioState.DISPOSED)
        )
        assert refs[4].current is False
        assert refs[5].current is False

    asyncio.run(scenario())

    assert ("audio_status", "playing") in setter_values
    assert ("audio_status", "completed") in setter_values
    assert ("audio_status", "error") in setter_values
    assert _keyed(view, "vocabulary-empty") is not None


def test_stale_play_cleanup_cannot_clear_a_newer_play_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.vocabulary_lookup_id = str(LOOKUP_ID)
    old_started = asyncio.Event()
    old_release = asyncio.Event()
    new_started = asyncio.Event()
    new_release = asyncio.Event()
    play_calls = 0

    class Controller:
        def session_snapshot(self):
            return state.token, state.auth_session_generation

        def session_is_current(self, token: str, generation: int) -> bool:
            return (
                state.token == token
                and state.auth_session_generation == generation
            )

        async def pronunciation(self):
            raise AssertionError("prepared playback must not refetch")

    async def play(page, *, timeout: float) -> None:
        nonlocal play_calls
        play_calls += 1
        if play_calls == 1:
            old_started.set()
            await old_release.wait()
        else:
            new_started.set()
            await new_release.wait()

    monkeypatch.setattr(vocabulary_screen, "play_prepared_audio", play)
    view, refs, _, _ = _render_screen(
        monkeypatch,
        state,
        Controller(),
        ["bom dia", _lookup(), "success", "Tradução pronta.", "ready", ""],
    )
    refs[3].current = b"ID3-pronunciation"
    refs[5].current = True
    speaker = _keyed(view, "vocabulary-pronunciation")

    async def scenario() -> None:
        old = asyncio.create_task(speaker.on_click(None))
        await old_started.wait()

        refs[2].current += 1
        refs[4].current = False
        newer = asyncio.create_task(speaker.on_click(None))
        await new_started.wait()
        newer_signal = refs[6].current

        old_release.set()
        await old
        assert refs[6].current is newer_signal

        newer_signal.set()
        new_release.set()
        await newer

    asyncio.run(scenario())

    assert play_calls == 2


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


def test_generated_audio_helpers_prepare_then_play_with_bounded_invoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class Audio:
        src: str | bytes = "https://quiz-media.example/question.mp3"
        on_loaded = None

        async def pause(self):
            calls.append("pause")

        async def _invoke_method(self, **kwargs):
            calls.append(kwargs)

        def update(self):
            calls.append("update")
            if isinstance(self.src, bytes) and self.on_loaded is not None:
                self.on_loaded(None)

    audio = Audio()
    monkeypatch.setattr(media_service, "ensure_audio", lambda page: audio)

    with pytest.raises(ValueError):
        asyncio.run(media_service.prepare_audio_bytes(object(), b""))

    asyncio.run(media_service.prepare_audio_bytes(object(), b"ID3-audio"))
    assert audio.src == b"ID3-audio"
    assert calls == ["update", "update"]

    asyncio.run(media_service.play_prepared_audio(object(), timeout=0.25))
    assert calls[-1] == {
        "method_name": "play",
        "arguments": {"position": 0},
        "timeout": 0.25,
    }

    asyncio.run(media_service.reset_audio_source(object()))
    assert audio.src == media_service.PLACEHOLDER_SRC
    assert calls[-2:] == ["pause", "update"]


def test_generated_audio_prepare_timeout_restores_previous_loaded_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = object()

    class Audio:
        src: str | bytes = media_service.PLACEHOLDER_SRC
        on_loaded = previous

        def update(self):
            return None

    audio = Audio()
    monkeypatch.setattr(media_service, "ensure_audio", lambda page: audio)

    with pytest.raises(TimeoutError):
        asyncio.run(
            media_service.prepare_audio_bytes(
                object(),
                b"ID3-audio",
                timeout=0.001,
            )
        )

    assert audio.on_loaded is previous


def test_generated_audio_prepare_retry_forces_a_source_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Audio:
        src: str | bytes = media_service.PLACEHOLDER_SRC
        on_loaded = None
        byte_updates = 0

        def update(self):
            if self.on_loaded is None:
                return
            if isinstance(self.src, bytes):
                self.byte_updates += 1
                if self.byte_updates > 1:
                    self.on_loaded(None)
            else:
                self.on_loaded(None)

    audio = Audio()
    monkeypatch.setattr(media_service, "ensure_audio", lambda page: audio)

    with pytest.raises(TimeoutError):
        asyncio.run(
            media_service.prepare_audio_bytes(
                object(),
                b"ID3-audio",
                timeout=0.001,
            )
        )

    asyncio.run(
        media_service.prepare_audio_bytes(
            object(),
            b"ID3-audio",
            timeout=0.1,
        )
    )

    assert audio.src == b"ID3-audio"
    assert audio.byte_updates == 2


def test_stale_audio_prepare_cannot_overwrite_a_newer_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[tuple[str | bytes, object]] = []

    class Audio:
        src: str | bytes = b"old-audio"
        on_loaded = None

        def update(self):
            if self.on_loaded is not None:
                updates.append((self.src, self.on_loaded))

    audio = Audio()
    old_is_current = True
    monkeypatch.setattr(media_service, "ensure_audio", lambda page: audio)

    async def scenario() -> tuple[bool, bool]:
        nonlocal old_is_current
        old = asyncio.create_task(
            media_service.prepare_audio_bytes(
                object(),
                b"old-audio",
                timeout=0.5,
                is_current=lambda: old_is_current,
            )
        )
        while len(updates) < 1:
            await asyncio.sleep(0)

        old_is_current = False
        newer = asyncio.create_task(
            media_service.prepare_audio_bytes(
                object(),
                b"new-audio",
                timeout=0.5,
                is_current=lambda: True,
            )
        )
        while len(updates) < 2:
            await asyncio.sleep(0)

        updates[1][1](None)
        newer_result = await newer
        updates[0][1](None)
        old_result = await old
        return old_result, newer_result

    old_result, newer_result = asyncio.run(scenario())

    assert old_result is False
    assert newer_result is True
    assert audio.src == b"new-audio"


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
        assert protected_route_key(routes[0]) == "/vocabulario"


def test_vocabulary_account_destination_passes_the_protected_route_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _authenticated_state()
    state.auth_validation_status = "valid"
    state.auth_validation_route = "/vocabulario"
    page = SimpleNamespace(route="/vocabulario", navigate=lambda route: None)
    monkeypatch.setattr(vocabulary_screen.ft, "context", SimpleNamespace(page=page))

    rendered = AuthGuard.__wrapped__(
        state,
        SimpleNamespace(),
        lambda: "vocabulary-screen",
    )

    assert rendered == "vocabulary-screen"
    assert protected_route_key("/vocabulario?from=account#translation") == (
        "/vocabulario"
    )
