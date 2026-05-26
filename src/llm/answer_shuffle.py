"""
Answer option shuffling for generated quiz questions.

Shuffles the order of answer options in each question while keeping
correct_index pointing to the same correct answer after the shuffle.

Tracking uses original index positions — not answer text — so the result
is correct even when multiple options share identical text.
"""
from __future__ import annotations
import random


def shuffle_options(
    question: dict,
    rng: random.Random | None = None,
) -> dict:
    """
    Return a new question dict with shuffled options and updated correct_index.
    The original dict is not modified.

    Returns the question unchanged if the structure is invalid
    (non-list options, fewer than 2 options, or out-of-range correct_index).
    Structural validation is the responsibility of validate_quiz / quiz_model.
    """
    options = question.get("options")
    correct_index = question.get("correct_index")

    if not isinstance(options, list) or len(options) < 2:
        return question
    if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
        return question

    _rng = rng or random.Random()

    # Shuffle a list of original positions so we can track correct_index exactly.
    # Using positions (not option text) handles duplicate option strings correctly.
    positions = list(range(len(options)))
    _rng.shuffle(positions)

    shuffled_options = [options[i] for i in positions]
    new_correct_index = positions.index(correct_index)

    return {
        **question,
        "options": shuffled_options,
        "correct_index": new_correct_index,
    }


def shuffle_quiz_options(
    quiz: dict,
    rng: random.Random | None = None,
) -> dict:
    """
    Return a new quiz dict with all question options shuffled.
    The original dict is not modified.

    A single rng instance is reused across all questions so that a seeded
    rng produces a fully deterministic result for the entire quiz.
    """
    questions = quiz.get("questions")
    if not isinstance(questions, list):
        return quiz

    _rng = rng or random.Random()
    shuffled_questions = [shuffle_options(q, _rng) for q in questions]

    return {
        **quiz,
        "questions": shuffled_questions,
    }
