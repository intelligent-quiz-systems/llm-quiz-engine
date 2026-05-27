"""
Guardrail context builder for quiz generation.

Formats a list of previously generated questions into a prompt snippet
so the model can avoid repeating topics across sequential generation calls.

Used by generate_quiz() when previous_questions are provided.
"""
from __future__ import annotations
from typing import TypedDict

# Module-level default — matches generation_config.GUARDRAIL_MAX_QUESTIONS.
# Defined here so this module can be imported without loading the llm package init.
GUARDRAIL_MAX_QUESTIONS: int = 100

_EMPTY_TEXT = "(none)"


class GuardrailContext(TypedDict):
    question_count: int   # number of questions included
    chars: int            # character count of the formatted text
    text: str             # text ready for prompt insertion
    truncated: bool       # True if input list was longer than max_questions


def build_guardrail_context(
    questions: list[str],
    max_questions: int = GUARDRAIL_MAX_QUESTIONS,
) -> GuardrailContext:
    """
    Build guardrail context from a list of question texts.

    Takes the most recent `max_questions` entries to control prompt length.
    Returns a GuardrailContext ready to be interpolated into a prompt template.
    """
    if not questions:
        return GuardrailContext(
            question_count=0,
            chars=len(_EMPTY_TEXT),
            text=_EMPTY_TEXT,
            truncated=False,
        )

    truncated = len(questions) > max_questions
    used = questions[-max_questions:]  # most recent questions
    lines = [f"- {q.strip()}" for q in used if q.strip()]
    text = "\n".join(lines) if lines else _EMPTY_TEXT

    return GuardrailContext(
        question_count=len(lines),
        chars=len(text),
        text=text,
        truncated=truncated,
    )


def extract_question_texts(quiz_json: dict) -> list[str]:
    """
    Extract question text strings from a raw quiz dict (as returned by generate_quiz).
    Convenience helper for building the previous_questions list between calls.
    """
    questions = quiz_json.get("questions", []) if isinstance(quiz_json, dict) else []
    return [q.get("question", "").strip() for q in questions if q.get("question")]


def format_guardrail_log(ctx: GuardrailContext) -> str:
    """Return a one-block log string for stdout."""
    return (
        f"guardrail_question_count: {ctx['question_count']}\n"
        f"guardrail_chars:          {ctx['chars']}\n"
        f"guardrail_truncated:      {ctx['truncated']}"
    )
