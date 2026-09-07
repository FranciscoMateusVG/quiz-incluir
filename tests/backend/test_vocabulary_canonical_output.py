"""Canonical vocabulary output shared by lookup and pronunciation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "app" / "shared"))

from quiz_shared.schemas import (  # noqa: E402
    VocabularyLookupResponse,
    validate_canonical_vocabulary_output,
)


def _response(**overrides: str) -> VocabularyLookupResponse:
    fields: dict[str, object] = {
        "lookup_id": uuid4(),
        "source_text": "ação diária",
        "translation": "daily action",
        "definition": "An action performed every day.",
    }
    fields.update(overrides)
    return VocabularyLookupResponse(**fields)


class CanonicalVocabularyOutputTests(unittest.TestCase):
    def test_accepts_nfc_accents_and_single_ascii_spaces(self) -> None:
        for value in ("good morning", "ação diária"):
            with self.subTest(value=value):
                self.assertEqual(validate_canonical_vocabulary_output(value), value)

        response = _response()
        self.assertEqual(response.source_text, "ação diária")
        self.assertEqual(response.translation, "daily action")

    def test_translation_rejects_repeated_spaces_and_nbsp(self) -> None:
        for translation in ("good  morning", "good\N{NO-BREAK SPACE}morning"):
            with self.subTest(translation=translation):
                with self.assertRaises(ValidationError):
                    _response(translation=translation)

    def test_definition_uses_the_same_whitespace_contract(self) -> None:
        for definition in (
            "An  ordinary definition.",
            "An\N{NO-BREAK SPACE}ordinary definition.",
        ):
            with self.subTest(definition=definition):
                with self.assertRaises(ValidationError):
                    _response(definition=definition)

    def test_outer_padding_and_non_nfc_text_remain_rejected(self) -> None:
        for translation in (
            " daily action",
            "daily action ",
            "ac\N{COMBINING CEDILLA}ão",
        ):
            with self.subTest(translation=translation):
                with self.assertRaises(ValidationError):
                    _response(translation=translation)

    def test_field_specific_length_bounds_remain_enforced(self) -> None:
        self.assertEqual(len(_response(translation="x" * 120).translation), 120)
        self.assertEqual(len(_response(definition="x" * 240).definition), 240)

        with self.assertRaises(ValidationError):
            _response(translation="x" * 121)
        with self.assertRaises(ValidationError):
            _response(definition="x" * 241)


if __name__ == "__main__":
    unittest.main()
