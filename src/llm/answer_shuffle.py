"""
Answer option shuffling for generated quiz questions.

Shuffles the order of answer options in each question while keeping
correct_index pointing to the same correct answer after the shuffle.

Tracking uses original index positions — not answer text — so the result
is correct even when multiple options share identical text.

shuffle_quiz_options_balanced() additionally guarantees that no answer
position is over-represented as the correct answer across the quiz,
eliminating the model's tendency to always put the correct answer first.
"""
from __future__ import annotations
import math
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


# ── Balanced shuffle ──────────────────────────────────────────────────────────

def _shuffle_to_target(
    question: dict,
    target_correct_index: int,
    rng: random.Random,
) -> dict:
    """
    Return a new question dict where the correct answer is at target_correct_index.

    Wrong answers fill the remaining slots in a random order.
    The original dict is not modified.
    Returns question unchanged if the structure is invalid or target is out of range.
    """
    options = question.get("options")
    correct_index = question.get("correct_index")

    if not isinstance(options, list) or len(options) < 2:
        return question
    if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
        return question
    if not (0 <= target_correct_index < len(options)):
        return question

    correct_option = options[correct_index]
    wrong_options = [options[i] for i in range(len(options)) if i != correct_index]
    rng.shuffle(wrong_options)

    new_options: list = [None] * len(options)
    new_options[target_correct_index] = correct_option
    wrong_iter = iter(wrong_options)
    for i in range(len(options)):
        if i != target_correct_index:
            new_options[i] = next(wrong_iter)

    return {**question, "options": new_options, "correct_index": target_correct_index}


def shuffle_quiz_options_balanced(
    quiz: dict,
    rng: random.Random | None = None,
) -> dict:
    """
    Return a new quiz dict with shuffled options and a balanced correct_index
    distribution. The original dict is not modified.

    Uses ceil(n / n_options) copies of each position in the target pool, which
    guarantees no position is overrepresented. For 4-option questions the max
    concentration is ceil(n/4)/n ≈ 25%, well under the 35% quality threshold.

    A single rng instance is reused across all questions so that a seeded rng
    produces a fully deterministic result for the entire quiz.
    """
    questions = quiz.get("questions")
    if not isinstance(questions, list) or not questions:
        return quiz

    _rng = rng or random.Random()
    n = len(questions)

    # Determine option count from the first structurally valid question
    n_options = 4
    for q in questions:
        opts = q.get("options")
        if isinstance(opts, list) and len(opts) >= 2:
            n_options = len(opts)
            break

    # Build a balanced pool of target correct_index values.
    # ceil(n / n_options) copies of each position gives enough items to cover n
    # without any position exceeding ceil(n / n_options) in the final assignment.
    items_per_pos = math.ceil(n / n_options)
    pool = (list(range(n_options)) * items_per_pos)[:n + n_options]
    _rng.shuffle(pool)
    targets = pool[:n]

    shuffled_questions = []
    for i, q in enumerate(questions):
        opts = q.get("options")
        n_opts = len(opts) if isinstance(opts, list) and len(opts) >= 2 else n_options
        target = targets[i] % n_opts
        shuffled_questions.append(_shuffle_to_target(q, target, _rng))

    return {**quiz, "questions": shuffled_questions}
