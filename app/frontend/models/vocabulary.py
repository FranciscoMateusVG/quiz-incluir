"""Typed frontend models for the Phase B vocabulary contract."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VocabularyLookup(BaseModel):
    """Canonical translation plus an opaque, short-lived audio grant."""

    model_config = ConfigDict(extra="forbid")

    source_text: str = Field(min_length=1, max_length=120)
    translation: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=1, max_length=240)
    lookup_id: UUID


__all__ = ["VocabularyLookup"]
