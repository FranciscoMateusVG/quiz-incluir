"""Builds a per-question PDF review of a finished quiz attempt.

Per-type answer/correct-answer/explanation extraction is delegated to
:mod:`app.core.question_types`. Explanations are only ever present in
``question.config["explanations"]`` (one entry per option, seeded exclusively
by ``seed_ai.py``) — omitted entirely when absent rather than faked.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape

import httpx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from app.core.grading import normalize_score, normalized_max_score
from app.core.question_types import HANDLERS, parse_config
from app.models import Answer, MediaType, Question, QuestionMedia, Quiz, QuizAttempt, QuizMedia

_MEDIA_FETCH_TIMEOUT = 10.0
_MAX_IMAGE_WIDTH = 14 * cm
_MAX_IMAGE_HEIGHT = 9 * cm


@dataclass
class ReportRow:
    question: Question
    media: list[QuestionMedia] = field(default_factory=list)
    answer: Answer | None = None


def _esc(text: object) -> str:
    return escape(str(text if text is not None else ""))


def _nl2br(text: str) -> str:
    return text.replace("\n", "<br/>")


def _user_answer_text(question: Question, answer: Answer | None) -> str:
    if answer is None:
        return "No answer submitted"
    handler = HANDLERS.get(question.type)
    if handler is None:
        return "Unsupported question type"
    return handler.format_response(answer.response or {})


def _fetch_text(url: str) -> str | None:
    try:
        resp = httpx.get(url, timeout=_MEDIA_FETCH_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def _fetch_image_flowable(url: str) -> Image | None:
    try:
        resp = httpx.get(url, timeout=_MEDIA_FETCH_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        raw = resp.content
        reader = ImageReader(io.BytesIO(raw))
        width, height = reader.getSize()
        if not width or not height:
            return None
        scale = min(_MAX_IMAGE_WIDTH / width, _MAX_IMAGE_HEIGHT / height, 1.0)
        return Image(io.BytesIO(raw), width=width * scale, height=height * scale)
    except Exception:
        return None


def _media_flowables(medias: list[QuestionMedia] | list[QuizMedia], styles) -> list:
    flowables: list = []
    for media in sorted(medias, key=lambda m: m.position):
        if media.type == MediaType.IMAGE and media.url:
            image = _fetch_image_flowable(media.url)
            if image is not None:
                flowables.append(image)
            elif media.caption:
                flowables.append(Paragraph(f"[image] {_esc(media.caption)}", styles["MediaCaption"]))
            else:
                flowables.append(Paragraph("[image unavailable]", styles["MediaCaption"]))
            flowables.append(Spacer(1, 4))
        elif media.type == MediaType.TEXT and (media.caption or media.url):
            text = (media.url and _fetch_text(media.url)) or media.caption or ""
            if text:
                flowables.append(Paragraph(_nl2br(_esc(text)), styles["MediaText"]))
                flowables.append(Spacer(1, 4))
    return flowables


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("QTitle", parent=styles["Heading3"], spaceBefore=14, spaceAfter=4))
    styles.add(ParagraphStyle("Prompt", parent=styles["BodyText"], fontSize=11, leading=15))
    styles.add(ParagraphStyle("AnswerCorrect", parent=styles["BodyText"], textColor="#1a7f37"))
    styles.add(ParagraphStyle("AnswerWrong", parent=styles["BodyText"], textColor="#c0392b"))
    styles.add(ParagraphStyle("CorrectAnswer", parent=styles["BodyText"], textColor="#1a1a1a"))
    styles.add(ParagraphStyle("Explanation", parent=styles["BodyText"], fontSize=9, textColor="#444444", leftIndent=8))
    styles.add(ParagraphStyle("MediaCaption", parent=styles["Italic"], fontSize=9, textColor="#666666"))
    styles.add(ParagraphStyle("MediaText", parent=styles["BodyText"], fontSize=10))
    return styles


def build_attempt_report(
    quiz: Quiz,
    attempt: QuizAttempt,
    max_score: float,
    rows: list[ReportRow],
) -> bytes:
    buffer = io.BytesIO()
    styles = _build_styles()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Quiz report - {quiz.title}",
    )

    display_score = normalize_score(attempt.score, max_score) or 0.0
    display_max = normalized_max_score(max_score)
    story: list = [
        Paragraph(_esc(quiz.title), styles["Title"]),
        Spacer(1, 6),
        Paragraph(
            f"Score: {display_score:g} / {display_max:g}"
            f" &mdash; generated {datetime.now():%Y-%m-%d %H:%M}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]

    # Shared context for the whole quiz (e.g. a reading passage or listening
    # audio clip) renders once here, up front — as opposed to each question's
    # own ReportRow.media (a vocabulary-style per-question illustration),
    # which renders per-question below.
    story.extend(_media_flowables(quiz.media, styles))
    if quiz.media:
        story.append(Spacer(1, 8))

    for index, row in enumerate(rows, start=1):
        question = row.question
        story.append(Paragraph(f"Question {index}", styles["QTitle"]))
        story.extend(_media_flowables(row.media, styles))
        story.append(Paragraph(_esc(question.prompt), styles["Prompt"]))
        story.append(Spacer(1, 4))

        is_correct = bool(row.answer and row.answer.is_correct)
        answer_style = styles["AnswerCorrect"] if is_correct else styles["AnswerWrong"]
        story.append(
            Paragraph(
                f"Your answer: {_esc(_user_answer_text(question, row.answer))}",
                answer_style,
            )
        )

        if not is_correct:
            handler = HANDLERS.get(question.type)
            config = parse_config(question) if handler else None
            if handler is not None and config is not None:
                breakdown = handler.option_breakdown(config)
                if breakdown is not None:
                    for option_text, option_correct, explanation in breakdown:
                        style = styles["CorrectAnswer"] if option_correct else styles["AnswerWrong"]
                        if option_correct:
                            label = "Correct"
                        elif explanation:
                            label = f"Incorrect: {_esc(explanation)}"
                        else:
                            label = "Incorrect"
                        story.append(Paragraph(f"{_esc(option_text)} ({label})", style))
                        if option_correct and explanation:
                            story.append(Paragraph(_esc(explanation), styles["Explanation"]))
                else:
                    correct_text = handler.correct_answer_text(config)
                    if correct_text is not None:
                        story.append(
                            Paragraph(f"Correct answer: {_esc(correct_text)}", styles["CorrectAnswer"])
                        )
                    explanation = handler.explanation_text(config)
                    if explanation:
                        story.append(Paragraph(_esc(explanation), styles["Explanation"]))

        story.append(Spacer(1, 10))

    doc.build(story)
    return buffer.getvalue()
