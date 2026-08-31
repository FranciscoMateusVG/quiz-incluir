"""Enums shared by the backend (SQLModel table columns) and frontend (API response parsing)."""

from __future__ import annotations

from enum import Enum


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECTION = "multiple_selection"
    TRUE_FALSE = "true_false"
    SHORT_TEXT = "short_text"


class MediaType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class LanguageLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class CourseLevel(str, Enum):
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"


class QuizCategory(str, Enum):
    READING = "reading"
    LISTENING = "listening"
    VOCABULARY_GRAMMAR = "vocabulary_grammar"


class UserRole(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"
