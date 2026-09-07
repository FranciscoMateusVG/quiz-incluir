"""Fixed, private OpenAI transport for Phase B vocabulary operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.ai_budget import LOOKUP_MAX_INPUT_TOKENS, LOOKUP_MAX_OUTPUT_TOKENS
from quiz_shared.schemas import VocabularyLookupResponse


PROVIDER_BASE_URL = "https://api.openai.com/v1"
TEXT_MODEL = "gpt-4o-mini-2024-07-18"
TTS_MODEL = "tts-1"
TTS_VOICE = "alloy"
MAX_PROVIDER_JSON_BYTES = 65_536
MAX_PROVIDER_AUDIO_BYTES = 2_097_152
MAX_CONSTRUCTED_PROMPT_UTF8_BYTES = 2_048
MAX_COMPLETION_TOKENS = LOOKUP_MAX_OUTPUT_TOKENS
PROVIDER_TIMEOUT_SECONDS = 10.0
MAX_RETRY_AFTER_SECONDS = 2_678_400

_SYSTEM_PROMPT = (
    "Translate the supplied Portuguese word or short phrase into one natural "
    "English equivalent and give one concise English definition sentence. "
    "Return only the required JSON fields. Do not include alternatives, "
    "examples, phonetics, markdown, or personal data."
)


@dataclass(frozen=True)
class ProviderLookupResult:
    translation: str
    definition: str
    input_tokens: int
    output_tokens: int


class VocabularyProvider(Protocol):
    async def lookup(self, text: str) -> ProviderLookupResult: ...

    async def pronounce(self, translation: str) -> bytes: ...


class ProviderFailure(Exception):
    def __init__(
        self,
        message: str,
        *,
        charge_known_absent: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.charge_known_absent = charge_known_absent
        self.retry_after_seconds = retry_after_seconds


class ProviderRateLimited(ProviderFailure):
    pass


class ProviderUnavailable(ProviderFailure):
    pass


class ProviderInvalidResponse(ProviderFailure):
    pass


class ProviderNoResult(ProviderFailure):
    pass


class _StructuredVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    translation: str
    definition: str


def _lookup_parameters(text: str) -> dict[str, object]:
    parameters: dict[str, object] = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "vocabulary_lookup",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["translation", "definition"],
                    "properties": {
                        "translation": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 120,
                        },
                        "definition": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 240,
                        },
                    },
                },
            },
        },
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "store": False,
        "temperature": 0,
    }
    encoded = json.dumps(parameters, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_CONSTRUCTED_PROMPT_UTF8_BYTES:
        raise ProviderInvalidResponse(
            "constructed prompt exceeded bound", charge_known_absent=True
        )
    return parameters


def _new_provider_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=PROVIDER_BASE_URL,
        timeout=httpx.Timeout(PROVIDER_TIMEOUT_SECONDS),
        trust_env=False,
        follow_redirects=False,
    )


def _retry_after(headers: httpx.Headers) -> int | None:
    value = headers.get("retry-after")
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value)
    if parsed <= 0:
        return None
    return min(parsed, MAX_RETRY_AFTER_SECONDS)


def _map_provider_exception(exc: Exception) -> ProviderFailure:
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return ProviderRateLimited(
                "provider rate limited",
                charge_known_absent=True,
                retry_after_seconds=_retry_after(exc.response.headers),
            )
        if exc.status_code in (401, 403):
            return ProviderUnavailable(
                "provider credential rejected", charge_known_absent=True
            )
        if 400 <= exc.status_code < 500:
            return ProviderInvalidResponse(
                "provider rejected fixed request", charge_known_absent=True
            )
        return ProviderUnavailable(
            "provider server unavailable", charge_known_absent=False
        )
    if isinstance(exc, (APIConnectionError, APITimeoutError, httpx.HTTPError)):
        return ProviderUnavailable(
            "provider transport unavailable", charge_known_absent=False
        )
    return ProviderInvalidResponse(
        "provider response unavailable", charge_known_absent=False
    )


async def _read_capped(response: object, maximum: int) -> bytes:
    content = bytearray()
    iterator = getattr(response, "aiter_bytes", None)
    if iterator is None:
        iterator = getattr(response, "iter_bytes", None)
    if iterator is None:
        raise ProviderInvalidResponse(
            "provider response is not streamable", charge_known_absent=False
        )
    async for chunk in iterator():
        if len(content) + len(chunk) > maximum:
            raise ProviderInvalidResponse(
                "provider response exceeded byte cap", charge_known_absent=False
            )
        content.extend(chunk)
    return bytes(content)


def is_valid_mp3(audio: bytes) -> bool:
    if not audio or len(audio) > MAX_PROVIDER_AUDIO_BYTES:
        return False
    return audio.startswith(b"ID3") or (
        len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0
    )


class OpenAIVocabularyProvider:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("provider credential is empty")
        self._api_key = api_key

    async def lookup(self, text: str) -> ProviderLookupResult:
        parameters = _lookup_parameters(text)
        http_client = _new_provider_http_client()
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=PROVIDER_BASE_URL,
            max_retries=0,
            timeout=PROVIDER_TIMEOUT_SECONDS,
            http_client=http_client,
        )
        try:
            async with client:
                async with client.chat.completions.with_streaming_response.create(
                    **parameters,
                ) as response:
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    if content_type != "application/json":
                        raise ProviderInvalidResponse(
                            "provider returned wrong response type",
                            charge_known_absent=False,
                        )
                    raw = await _read_capped(response, MAX_PROVIDER_JSON_BYTES)
        except ProviderFailure:
            raise
        except Exception as exc:
            raise _map_provider_exception(exc) from exc

        try:
            envelope = json.loads(raw)
            choice = envelope["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise ProviderNoResult(
                    "provider declined lookup", charge_known_absent=False
                )
            structured = _StructuredVocabulary.model_validate_json(message["content"])
            usage = envelope["usage"]
            input_tokens = usage["prompt_tokens"]
            output_tokens = usage["completion_tokens"]
            if (
                isinstance(input_tokens, bool)
                or not isinstance(input_tokens, int)
                or not 0 <= input_tokens <= LOOKUP_MAX_INPUT_TOKENS
                or isinstance(output_tokens, bool)
                or not isinstance(output_tokens, int)
                or not 0 <= output_tokens <= MAX_COMPLETION_TOKENS
            ):
                raise ValueError("invalid usage")
            validated = VocabularyLookupResponse.model_validate(
                {
                    "lookup_id": "00000000-0000-4000-8000-000000000000",
                    "source_text": text,
                    "translation": structured.translation,
                    "definition": structured.definition,
                }
            )
        except ProviderNoResult:
            raise
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            raise ProviderInvalidResponse(
                "provider returned malformed lookup", charge_known_absent=False
            ) from exc
        return ProviderLookupResult(
            translation=validated.translation,
            definition=validated.definition,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def pronounce(self, translation: str) -> bytes:
        http_client = _new_provider_http_client()
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=PROVIDER_BASE_URL,
            max_retries=0,
            timeout=PROVIDER_TIMEOUT_SECONDS,
            http_client=http_client,
        )
        try:
            async with client:
                async with client.audio.speech.with_streaming_response.create(
                    model=TTS_MODEL,
                    voice=TTS_VOICE,
                    input=translation,
                    response_format="mp3",
                    speed=0.9,
                ) as response:
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    if content_type != "audio/mpeg":
                        raise ProviderInvalidResponse(
                            "provider returned wrong audio type",
                            charge_known_absent=False,
                        )
                    audio = await _read_capped(response, MAX_PROVIDER_AUDIO_BYTES)
        except ProviderFailure:
            raise
        except Exception as exc:
            raise _map_provider_exception(exc) from exc
        if not is_valid_mp3(audio):
            raise ProviderInvalidResponse(
                "provider returned invalid audio", charge_known_absent=False
            )
        return audio
