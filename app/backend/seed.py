"""Seed the database with demo data.

Usage:
    .venv/bin/python seed.py              # seed if tables empty
    .venv/bin/python seed.py --reset      # wipe and reseed

Media URLs point to real, publicly reachable files (verified with curl before
being added here) instead of placeholder links, so every media type
(image/audio/video/text) actually renders in the frontend:
  - images: picsum.photos (real photos, deterministic per seed)
  - audio:  soundhelix.com sample tracks
  - video:  MDN's CC0 sample clips (interactive-examples.mdn.mozilla.net)
  - text:   inline caption only (no url) so it always renders, no fetch needed
"""

import asyncio
import sys
from datetime import datetime, timedelta, UTC

from sqlalchemy import delete
from sqlmodel import func, select

from app.core.database import async_session_maker, init_db
from models import (
    Answer,
    LanguageLevel,
    CourseLevel,
    MediaType,
    Question,
    QuestionMedia,
    QuizMedia,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizCategory,
    QuizQuestion,
    User,
)


async def clear_all(session) -> None:
    for model in (Answer, QuizAttempt, QuizQuestion, QuestionMedia, QuizMedia, Question, Quiz, User):
        await session.exec(delete(model))
    await session.commit()


async def has_data(session) -> bool:
    count = (await session.exec(select(func.count(User.id)))).one()
    return count > 0


async def seed() -> None:
    await init_db()
    async with async_session_maker() as session:
        if "--reset" in sys.argv:
            await clear_all(session)

        if await has_data(session):
            print("Database already has data. Use --reset to wipe and reseed.")
            return

        users = [
            User(email="anna@example.com", level=CourseLevel.B1),
            User(email="ben@example.com", level=CourseLevel.B1),
            User(email="elena@example.com", level=CourseLevel.B1),
            User(email="carla@example.com", level=CourseLevel.B1),
            User(email="felipe@example.com", level=CourseLevel.B1),
            User(email="diego@example.com", level=CourseLevel.B1),
            User(email="giulia@example.com", level=CourseLevel.B1),
        ]
        session.add_all(users)

        # -----------------------------------------------------------------
        # Questions, grouped by the quiz that will link to them (0-3, 4-7, ...)
        # -----------------------------------------------------------------
        questions = [
            # --- Beginner Basics (A1, vocabulary_grammar) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Which word is a fruit?",
                suggested_score=1.0,
                config={"options": ["apple", "table", "chair", "book"], "correct_index": 0},
            ),
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="What is the opposite of 'hot'?",
                suggested_score=1.0,
                config={"options": ["cold", "warm", "boiling", "sunny"], "correct_index": 0},
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="The sun rises in the east.",
                suggested_score=1.0,
                config={"answer": True},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Complete the sentence: I ____ a student.",
                suggested_score=1.0,
                config={"accepted_answers": ["am"]},
            ),
            # --- Intermediate Check (B1, listening) ---
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which of these are animals?",
                suggested_score=1.0,
                config={
                    "options": ["dog", "rose", "cat", "hammer"],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Choose the correct past tense: 'I ____ to school yesterday.'",
                suggested_score=1.0,
                config={"options": ["go", "went", "gone", "going"], "correct_index": 1},
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="'Their' and 'they're' mean the same thing.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Which word is a synonym of 'happy'?",
                suggested_score=1.0,
                config={"options": ["sad", "angry", "joyful", "tired"], "correct_index": 2},
            ),
            # --- Advanced Mastery (C1, reading) ---
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Give the correct comparative form of 'good'.",
                suggested_score=1.0,
                config={"accepted_answers": ["better"]},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which sentences are grammatically correct?",
                suggested_score=1.0,
                config={
                    "options": [
                        "She has been working all day.",
                        "He don't like coffee.",
                        "They have lived here for years.",
                        "Me go to the store.",
                    ],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Select the most formal way to request assistance.",
                suggested_score=1.0,
                config={
                    "options": [
                        "I would be grateful if you could help me.",
                        "Help me now.",
                        "Gimme a hand.",
                        "You need to help me.",
                    ],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Choose the word that best fits: 'His ______ disregard for rules alarmed his colleagues.'",
                suggested_score=1.0,
                config={
                    "options": ["flagrant", "lukewarm", "paltry", "bashful"],
                    "correct_index": 0,
                },
            ),
            # --- Everyday Vocabulary (A2, vocabulary_grammar) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="What do you use to write?",
                suggested_score=1.0,
                config={"options": ["pen", "spoon", "shoe", "cloud"], "correct_index": 0},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which of these are fruits?",
                suggested_score=1.0,
                config={
                    "options": ["banana", "car", "orange", "pencil"],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="A week has seven days.",
                suggested_score=1.0,
                config={"answer": True},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Complete: She ____ to the market every Sunday. (go)",
                suggested_score=1.0,
                config={"accepted_answers": ["goes"]},
            ),
            # --- Grammar in Practice (B2, vocabulary_grammar) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Choose the correct conditional: 'If I ___ more time, I would travel.'",
                suggested_score=1.0,
                config={"options": ["have", "had", "having", "has"], "correct_index": 1},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which sentences use the passive voice correctly?",
                suggested_score=1.0,
                config={
                    "options": [
                        "The cake was eaten by the children.",
                        "The children eaten the cake.",
                        "The report was written by her.",
                        "She written the report.",
                    ],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="'Fewer' is used with countable nouns and 'less' with uncountable nouns.",
                suggested_score=1.0,
                config={"answer": True},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Rewrite in reported speech: She said, 'I am tired.' -> She said that she ____ tired.",
                suggested_score=1.0,
                config={"accepted_answers": ["was"]},
            ),
            # --- Reading Comprehension (B1, reading) ---
            # Refers to the shared QuizMedia reading passage attached below.
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Where did Marta travel for her work assignment?",
                suggested_score=1.0,
                config={"options": ["Lisbon", "Madrid", "Paris", "Rome"], "correct_index": 0},
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="Marta had traveled abroad many times before this trip.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which of these did Marta do during her trip?",
                suggested_score=1.0,
                config={
                    "options": [
                        "Got lost",
                        "Learned to order coffee",
                        "Bought a car",
                        "Asked for directions",
                    ],
                    "correct_indices": [0, 1, 3],
                },
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt=(
                    "Complete: A friendly ____ helped Marta find the tram station. "
                    "(a person who sells things in a shop)"
                ),
                suggested_score=1.0,
                config={"accepted_answers": ["shopkeeper"]},
            ),
            # --- Mastery Listening (C2, listening) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Choose the word closest in meaning to 'ubiquitous'.",
                suggested_score=1.0,
                config={
                    "options": ["omnipresent", "rare", "fragile", "temporary"],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which words are synonyms of 'meticulous'?",
                suggested_score=1.0,
                config={
                    "options": ["careless", "thorough", "precise", "sloppy"],
                    "correct_indices": [1, 2],
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="The idiom 'to bite the bullet' means to avoid a difficult situation.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Give a more formal synonym for 'find out'.",
                suggested_score=1.0,
                config={"accepted_answers": ["ascertain", "determine"]},
            ),
            # --- Travel Vocabulary (A1, vocabulary_grammar) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="What do you show at the airport before boarding?",
                suggested_score=1.0,
                config={
                    "options": ["passport", "umbrella", "spoon", "pillow"],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="A 'suitcase' is used to carry your clothes when you travel.",
                suggested_score=1.0,
                config={"answer": True},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which of these can you find at a hotel?",
                suggested_score=1.0,
                config={
                    "options": ["reception", "engine", "room", "tire"],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Complete: I need to buy a ____ to travel by plane. (ticket)",
                suggested_score=1.0,
                config={"accepted_answers": ["ticket"]},
            ),
            # --- Business English Basics (B1, vocabulary_grammar) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="What do you call a meeting to discuss work progress?",
                suggested_score=1.0,
                config={
                    "options": ["status meeting", "party", "vacation", "lunch break"],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which of these are common in a formal business email?",
                suggested_score=1.0,
                config={
                    "options": ["Dear Sir/Madam,", "Best regards,", "See ya,", "Kind regards,"],
                    "correct_indices": [0, 1, 3],
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="'CC' in an email means you are the only recipient.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Complete: Please find ____ the report you requested. (attached)",
                suggested_score=1.0,
                config={"accepted_answers": ["attached"]},
            ),
            # --- Short Stories (A2, reading) ---
            # Refers to the shared QuizMedia reading passage attached below.
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="Where did Tomas walk his dog?",
                suggested_score=1.0,
                config={
                    "options": ["In the park", "At the beach", "At school", "In a shop"],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="Tomas fed the birds alone every day.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="What happened in the story?",
                suggested_score=1.0,
                config={
                    "options": [
                        "Tomas saw an old man",
                        "Tomas bought a dog",
                        "The man fed the birds",
                        "They became friends",
                    ],
                    "correct_indices": [0, 2, 3],
                },
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Complete: The old man was ____ the birds when Tomas saw him. (feeding)",
                suggested_score=1.0,
                config={"accepted_answers": ["feeding"]},
            ),
            # --- Podcast Practice (B2, listening) ---
            Question(
                type=QuestionType.MULTIPLE_CHOICE,
                prompt="What is the main topic being discussed?",
                suggested_score=1.0,
                config={
                    "options": ["Remote work", "Cooking", "Sports", "Music"],
                    "correct_index": 0,
                },
            ),
            Question(
                type=QuestionType.MULTIPLE_SELECTION,
                prompt="Which benefits of remote work are mentioned?",
                suggested_score=1.0,
                config={
                    "options": ["Flexible hours", "Free lunch", "No commuting", "Company car"],
                    "correct_indices": [0, 2],
                },
            ),
            Question(
                type=QuestionType.TRUE_FALSE,
                prompt="The speaker says remote work has no downsides.",
                suggested_score=1.0,
                config={"answer": False},
            ),
            Question(
                type=QuestionType.SHORT_TEXT,
                prompt="Give a synonym for 'flexible' as used in the podcast.",
                suggested_score=1.0,
                config={"accepted_answers": ["adaptable", "versatile"]},
            ),
        ]
        session.add_all(questions)
        await session.flush()

        question_media = [
            QuestionMedia(
                question_id=questions[0].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/apple-fruit/640/480",
                caption="Fresh apples in a basket",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[1].id,
                type=MediaType.VIDEO,
                url="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
                caption="A short clip to think about while choosing your answer",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[2].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/sunrise-ocean/640/480",
                caption="Sunrise over the ocean",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[4].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/farm-animals/640/480",
                caption="Animals you might find on a farm",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[5].id,
                type=MediaType.AUDIO,
                url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                caption="Listen to the sentence",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[12].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/writing-pen/640/480",
                caption="A pen and notebook",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[13].id,
                type=MediaType.VIDEO,
                url="https://download.samplelib.com/mp4/sample-5s.mp4",
                caption="Watch the clip, then name the fruits you saw",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[16].id,
                type=MediaType.VIDEO,
                url="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/friday.mp4",
                caption="Watch the clip, then complete the conditional sentence",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[17].id,
                type=MediaType.TEXT,
                caption="Grammar tip: passive voice = object + be + past participle (+ by agent).",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[20].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/lisbon-travel/640/480",
                caption="A European city street",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[24].id,
                type=MediaType.AUDIO,
                url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
                caption="Listen carefully before answering",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[27].id,
                type=MediaType.AUDIO,
                url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
                caption="Listen and choose the best synonym",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[28].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/airport-travel/640/480",
                caption="Airport departure gate",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[32].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/office-business/640/480",
                caption="A busy office meeting",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[36].id,
                type=MediaType.IMAGE,
                url="https://picsum.photos/seed/park-birds/640/480",
                caption="A park where people feed the birds",
                position=0,
            ),
            QuestionMedia(
                question_id=questions[40].id,
                type=MediaType.AUDIO,
                url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
                caption="Listen to the podcast excerpt",
                position=0,
            ),
        ]

        quizzes = [
            Quiz(
                title="Beginner Basics",
                description="A1 level essentials",
                category=QuizCategory.VOCABULARY_GRAMMAR,
                level=LanguageLevel.A1,
            ),
            Quiz(
                title="Intermediate Check",
                description="B1 grammar and vocabulary",
                category=QuizCategory.LISTENING,
                level=LanguageLevel.B1,
            ),
            Quiz(
                title="Advanced Mastery",
                description="C1-C2 challenge",
                category=QuizCategory.READING,
                level=LanguageLevel.C1,
            ),
            Quiz(
                title="Everyday Vocabulary",
                description="A2 words for daily life",
                category=QuizCategory.VOCABULARY_GRAMMAR,
                level=LanguageLevel.A2,
            ),
            Quiz(
                title="Grammar in Practice",
                description="B2 conditionals, passive voice and reported speech",
                category=QuizCategory.VOCABULARY_GRAMMAR,
                level=LanguageLevel.B2,
            ),
            Quiz(
                title="Reading Comprehension",
                description="B1 short story with follow-up questions",
                category=QuizCategory.READING,
                level=LanguageLevel.B1,
            ),
            Quiz(
                title="Mastery Listening",
                description="C2 advanced vocabulary and idioms",
                category=QuizCategory.LISTENING,
                level=LanguageLevel.C2,
            ),
            Quiz(
                title="Travel Vocabulary",
                description="A1 words for airports, hotels and trips",
                category=QuizCategory.VOCABULARY_GRAMMAR,
                level=LanguageLevel.A1,
            ),
            Quiz(
                title="Business English Basics",
                description="B1 email and meeting vocabulary",
                category=QuizCategory.VOCABULARY_GRAMMAR,
                level=LanguageLevel.B1,
            ),
            Quiz(
                title="Short Stories",
                description="A2 short story with follow-up questions",
                category=QuizCategory.READING,
                level=LanguageLevel.A2,
            ),
            Quiz(
                title="Podcast Practice",
                description="B2 listening comprehension about remote work",
                category=QuizCategory.LISTENING,
                level=LanguageLevel.B2,
            ),
        ]
        session.add_all(quizzes)
        await session.flush()

        quiz_media = [
            QuizMedia(
                quiz_id=quizzes[2].id,
                type=MediaType.TEXT,
                caption=(
                    "Long before dawn, the harbor was already alive with movement. "
                    "Fishermen hauled in nets heavy with the night's catch while "
                    "merchants haggled over prices in low, urgent voices. A young "
                    "apprentice, barely older than fourteen, wove between the crates "
                    "and coiled ropes, absorbing every negotiation like a sponge. It "
                    "was here, amid the salt-crusted chaos of commerce, that he would "
                    "learn more about human nature than any classroom could ever "
                    "teach him."
                ),
                position=0,
            ),
            QuizMedia(
                quiz_id=quizzes[5].id,
                type=MediaType.TEXT,
                caption=(
                    "Marta had never traveled outside her hometown before, so when "
                    "her company offered her a two-week assignment in Lisbon, she "
                    "said yes immediately. She packed a small suitcase, printed her "
                    "tickets, and spent the flight practicing simple Portuguese "
                    "phrases. On her first morning, she got lost twice, but a "
                    "friendly shopkeeper helped her find the tram station. By the "
                    "end of the trip, Marta could order coffee, ask for directions, "
                    "and even joke a little in Portuguese."
                ),
                position=0,
            ),
            QuizMedia(
                quiz_id=quizzes[9].id,
                type=MediaType.TEXT,
                caption=(
                    "Every morning, Tomas walked his dog in the park near his house. "
                    "One day, he saw an old man feeding the birds. The man smiled and "
                    "said, 'Good morning! Would you like to help me?' Tomas said yes, "
                    "and from that day, they fed the birds together every morning."
                ),
                position=0,
            ),
        ]
        session.add_all(question_media)
        session.add_all(quiz_media)
        await session.flush()

        link_spec = [
            (quizzes[0], [0, 1, 2, 3]),
            (quizzes[1], [4, 5, 6, 7]),
            (quizzes[2], [8, 9, 10, 11]),
            (quizzes[3], [12, 13, 14, 15]),
            (quizzes[4], [16, 17, 18, 19]),
            (quizzes[5], [20, 21, 22, 23]),
            (quizzes[6], [24, 25, 26, 27]),
            (quizzes[7], [28, 29, 30, 31]),
            (quizzes[8], [32, 33, 34, 35]),
            (quizzes[9], [36, 37, 38, 39]),
            (quizzes[10], [40, 41, 42, 43]),
        ]
        for quiz, indices in link_spec:
            for position, index in enumerate(indices):
                session.add(
                    QuizQuestion(
                        quiz_id=quiz.id,
                        question_id=questions[index].id,
                        position=position,
                    )
                )

        attempts = [
            QuizAttempt(
                quiz_id=quizzes[0].id,
                user_id=users[0].id,
                started_at=datetime.now(UTC) - timedelta(days=2),
                finished_at=datetime.now(UTC) - timedelta(days=2),
                score=2.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[0].id,
                user_id=users[1].id,
                started_at=datetime.now(UTC) - timedelta(days=1),
                finished_at=None,
                score=None,
            ),
            QuizAttempt(
                quiz_id=quizzes[1].id,
                user_id=users[3].id,
                started_at=datetime.now(UTC) - timedelta(hours=3),
                finished_at=datetime.now(UTC) - timedelta(hours=3),
                score=3.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[2].id,
                user_id=users[5].id,
                started_at=datetime.now(UTC) - timedelta(hours=1),
                finished_at=None,
                score=None,
            ),
            QuizAttempt(
                quiz_id=quizzes[3].id,
                user_id=users[2].id,
                started_at=datetime.now(UTC) - timedelta(days=3),
                finished_at=datetime.now(UTC) - timedelta(days=3),
                score=3.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[4].id,
                user_id=users[4].id,
                started_at=datetime.now(UTC) - timedelta(hours=6),
                finished_at=None,
                score=None,
            ),
            QuizAttempt(
                quiz_id=quizzes[5].id,
                user_id=users[3].id,
                started_at=datetime.now(UTC) - timedelta(days=5),
                finished_at=datetime.now(UTC) - timedelta(days=5),
                score=4.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[6].id,
                user_id=users[6].id,
                started_at=datetime.now(UTC) - timedelta(hours=2),
                finished_at=datetime.now(UTC) - timedelta(hours=2),
                score=2.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[7].id,
                user_id=users[0].id,
                started_at=datetime.now(UTC) - timedelta(days=4),
                finished_at=datetime.now(UTC) - timedelta(days=4),
                score=4.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[8].id,
                user_id=users[5].id,
                started_at=datetime.now(UTC) - timedelta(minutes=45),
                finished_at=None,
                score=None,
            ),
            QuizAttempt(
                quiz_id=quizzes[9].id,
                user_id=users[2].id,
                started_at=datetime.now(UTC) - timedelta(days=6),
                finished_at=datetime.now(UTC) - timedelta(days=6),
                score=3.0,
            ),
            QuizAttempt(
                quiz_id=quizzes[10].id,
                user_id=users[4].id,
                started_at=datetime.now(UTC) - timedelta(hours=8),
                finished_at=datetime.now(UTC) - timedelta(hours=8),
                score=2.0,
            ),
        ]
        session.add_all(attempts)
        await session.flush()

        answers = [
            Answer(
                attempt_id=attempts[0].id,
                question_id=questions[0].id,
                response={"selected": "apple"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=2),
            ),
            Answer(
                attempt_id=attempts[0].id,
                question_id=questions[1].id,
                response={"selected": "cold"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=2),
            ),
            Answer(
                attempt_id=attempts[0].id,
                question_id=questions[2].id,
                response={"selected": True},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=2),
            ),
            Answer(
                attempt_id=attempts[0].id,
                question_id=questions[3].id,
                response={"text": "is"},
                is_correct=False,
                points_awarded=0.0,
                answered_at=datetime.now(UTC) - timedelta(days=2),
            ),
            Answer(
                attempt_id=attempts[2].id,
                question_id=questions[4].id,
                response={"selected": ["dog", "cat"]},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(hours=3),
            ),
            Answer(
                attempt_id=attempts[2].id,
                question_id=questions[5].id,
                response={"selected": "go"},
                is_correct=False,
                points_awarded=0.0,
                answered_at=datetime.now(UTC) - timedelta(hours=3),
            ),
            Answer(
                attempt_id=attempts[4].id,
                question_id=questions[12].id,
                response={"selected": "pen"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=3),
            ),
            Answer(
                attempt_id=attempts[4].id,
                question_id=questions[13].id,
                response={"selected": ["banana", "orange"]},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=3),
            ),
            Answer(
                attempt_id=attempts[6].id,
                question_id=questions[20].id,
                response={"selected": "Lisbon"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=5),
            ),
            Answer(
                attempt_id=attempts[6].id,
                question_id=questions[21].id,
                response={"selected": False},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=5),
            ),
            Answer(
                attempt_id=attempts[7].id,
                question_id=questions[24].id,
                response={"selected": "omnipresent"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(hours=2),
            ),
            Answer(
                attempt_id=attempts[7].id,
                question_id=questions[25].id,
                response={"selected": ["careless", "sloppy"]},
                is_correct=False,
                points_awarded=0.0,
                answered_at=datetime.now(UTC) - timedelta(hours=2),
            ),
            Answer(
                attempt_id=attempts[8].id,
                question_id=questions[28].id,
                response={"selected": "passport"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=4),
            ),
            Answer(
                attempt_id=attempts[8].id,
                question_id=questions[29].id,
                response={"selected": True},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=4),
            ),
            Answer(
                attempt_id=attempts[10].id,
                question_id=questions[36].id,
                response={"selected": "In the park"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(days=6),
            ),
            Answer(
                attempt_id=attempts[10].id,
                question_id=questions[37].id,
                response={"selected": True},
                is_correct=False,
                points_awarded=0.0,
                answered_at=datetime.now(UTC) - timedelta(days=6),
            ),
            Answer(
                attempt_id=attempts[11].id,
                question_id=questions[40].id,
                response={"selected": "Remote work"},
                is_correct=True,
                points_awarded=1.0,
                answered_at=datetime.now(UTC) - timedelta(hours=8),
            ),
            Answer(
                attempt_id=attempts[11].id,
                question_id=questions[41].id,
                response={"selected": ["Flexible hours", "Free lunch"]},
                is_correct=False,
                points_awarded=0.0,
                answered_at=datetime.now(UTC) - timedelta(hours=8),
            ),
        ]
        session.add_all(answers)

        await session.commit()
        print(
            f"Seeded: {len(users)} users, {len(questions)} questions, "
            f"{len(question_media)} question media, {len(quiz_media)} quiz media, "
            f"{len(quizzes)} quizzes, {len(attempts)} attempts, {len(answers)} answers"
        )


if __name__ == "__main__":
    asyncio.run(seed())
