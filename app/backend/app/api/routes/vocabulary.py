"""Authenticated vocabulary lookup and pronunciation endpoints."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.requests import ClientDisconnect

from app.api.deps import get_current_user
from app.core.ai_budget import AIBudgetRepository
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.vocabulary import (
    VocabularyGrantRepository,
    VocabularyService,
    VocabularyServiceError,
    normalize_lookup_text,
)
from app.core.vocabulary_provider import OpenAIVocabularyProvider, is_valid_mp3
from app.models import User
from quiz_shared.schemas import (
    PronunciationRequest,
    VocabularyErrorCode,
    VocabularyErrorResponse,
    VocabularyLookupRequest,
    VocabularyLookupResponse,
)


MAX_REQUEST_BODY_BYTES = 1_024
router = APIRouter()


class VocabularyAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: VocabularyErrorCode,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


async def vocabulary_api_error_handler(
    _request: Request, exc: VocabularyAPIError
) -> JSONResponse:
    body = VocabularyErrorResponse(
        code=exc.code,
        message=exc.message,
        retry_after_seconds=exc.retry_after_seconds,
    ).model_dump(mode="json", exclude_none=True)
    headers: dict[str, str] = {}
    if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS and exc.retry_after_seconds:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


_MESSAGES: dict[VocabularyErrorCode, tuple[int, str]] = {
    VocabularyErrorCode.INVALID_INPUT: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Informe uma palavra, frase ou consulta válida.",
    ),
    VocabularyErrorCode.NO_RESULT: (
        status.HTTP_404_NOT_FOUND,
        "Nenhuma tradução foi encontrada.",
    ),
    VocabularyErrorCode.RATE_LIMITED: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Limite de consultas atingido.",
    ),
    VocabularyErrorCode.PROVIDER_UNAVAILABLE: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Vocabulário indisponível no momento.",
    ),
    VocabularyErrorCode.INVALID_PROVIDER_RESPONSE: (
        status.HTTP_502_BAD_GATEWAY,
        "Não foi possível interpretar a resposta.",
    ),
}


def _translate_service_error(exc: VocabularyServiceError) -> VocabularyAPIError:
    status_code, message = _MESSAGES[exc.code]
    return VocabularyAPIError(
        status_code,
        exc.code,
        message,
        retry_after_seconds=exc.retry_after_seconds,
    )


def _invalid_input() -> VocabularyAPIError:
    status_code, message = _MESSAGES[VocabularyErrorCode.INVALID_INPUT]
    return VocabularyAPIError(status_code, VocabularyErrorCode.INVALID_INPUT, message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


async def _read_bounded_json(request: Request) -> Any:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1:
        raise _invalid_input()
    content_type = content_types[0]
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise _invalid_input()
    content_lengths = request.headers.getlist("content-length")
    if len(content_lengths) > 1:
        raise _invalid_input()
    if content_lengths:
        content_length = content_lengths[0]
        if (
            not content_length.isascii()
            or not content_length.isdecimal()
            or len(content_length) > 4
        ):
            raise _invalid_input()
        if int(content_length) > MAX_REQUEST_BODY_BYTES:
            raise _invalid_input()
    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
                raise _invalid_input()
            body.extend(chunk)
        if not body:
            raise _invalid_input()
        return json.loads(
            bytes(body).decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except VocabularyAPIError:
        raise
    except (
        ClientDisconnect,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise _invalid_input() from exc


@lru_cache
def get_vocabulary_service() -> VocabularyService:
    provider = None
    if settings.OPENAI_API_KEY is not None:
        api_key = settings.OPENAI_API_KEY.get_secret_value()
        if api_key and api_key.strip():
            provider = OpenAIVocabularyProvider(api_key)
    budget = AIBudgetRepository(
        async_session_maker,
        monthly_limit_microusd=settings.AI_MONTHLY_BUDGET_MICROUSD,
    )
    return VocabularyService(
        provider=provider,
        budget=budget,
        grants=VocabularyGrantRepository(async_session_maker),
        concurrency=4,
    )


@router.post("/lookup", response_model=VocabularyLookupResponse)
async def lookup_vocabulary(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[VocabularyService, Depends(get_vocabulary_service)],
) -> VocabularyLookupResponse:
    try:
        payload = VocabularyLookupRequest.model_validate(
            await _read_bounded_json(request)
        )
        source_text = normalize_lookup_text(payload.text)
    except (ValidationError, ValueError) as exc:
        raise _invalid_input() from exc
    try:
        return await service.lookup(current_user.id, source_text)
    except VocabularyServiceError as exc:
        raise _translate_service_error(exc) from exc


@router.post("/pronunciation")
async def pronounce_vocabulary(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[VocabularyService, Depends(get_vocabulary_service)],
) -> Response:
    try:
        payload = PronunciationRequest.model_validate(await _read_bounded_json(request))
    except ValidationError as exc:
        raise _invalid_input() from exc
    try:
        audio = await service.pronounce(current_user.id, payload.lookup_id)
    except VocabularyServiceError as exc:
        raise _translate_service_error(exc) from exc
    if not is_valid_mp3(audio):
        status_code, message = _MESSAGES[VocabularyErrorCode.INVALID_PROVIDER_RESPONSE]
        raise VocabularyAPIError(
            status_code,
            VocabularyErrorCode.INVALID_PROVIDER_RESPONSE,
            message,
        )
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
