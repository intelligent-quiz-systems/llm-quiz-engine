"""
Batch retry/fallback strategy for quiz generation.

Generates quiz questions in multiple API calls, reducing batch size
on failures and retrying according to the configured limits.

Error classification here is intentionally lightweight — it maps exceptions
to control-flow decisions (reduce/retry/halt) only. For full diagnostic
logging of error details, see the diagnostics/provider-error-details branch.
"""
from __future__ import annotations
from typing import Literal

import openai

# Decision type for batch control flow
Decision = Literal["accept", "retry", "reduce", "halt"]

# Module-level defaults — match generation_config.py values.
# Defined here so this module can be imported without triggering llm/__init__.py.
INITIAL_BATCH_SIZE          : int = 10
FALLBACK_BATCH_SIZE         : int = 5
MIN_BATCH_SIZE              : int = 1
MAX_ATTEMPTS_PER_BATCH_SIZE : int = 2


# ── Decision helpers (pure, testable without API) ─────────────────────────────

def classify_exception(exc: Exception) -> Decision:
    """
    Map an LLM API exception to a batch control-flow decision.
    Returns one of: 'reduce', 'retry', 'halt'.
    """
    if isinstance(exc, openai.RateLimitError):
        return "halt"
    if isinstance(exc, (openai.BadRequestError, openai.LengthFinishReasonError)):
        return "reduce"
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return "retry"
    if isinstance(exc, openai.ContentFilterFinishReasonError):
        return "halt"
    return "halt"


def reduce_batch_size(
    current: int,
    fallback: int = FALLBACK_BATCH_SIZE,
    minimum: int = MIN_BATCH_SIZE,
) -> int:
    """Return the next smaller batch size. Cannot go below minimum."""
    if current > fallback:
        return fallback
    if current > minimum:
        return minimum
    return minimum


def should_reduce(decision: Decision, attempts_at_size: int, max_attempts: int) -> bool:
    """Return True if batch size should be reduced now."""
    if decision == "halt":
        return False  # halt stops generation; does not trigger a size reduction
    if decision == "reduce":
        return True
    return attempts_at_size >= max_attempts  # "retry" exhausted → reduce


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batched_generation(
    topic: str,
    difficulty: str,
    num_questions: int,
    source_text: str | None = None,
    *,
    initial_batch_size: int = INITIAL_BATCH_SIZE,
    fallback_batch_size: int = FALLBACK_BATCH_SIZE,
    min_batch_size: int = MIN_BATCH_SIZE,
    max_attempts_per_size: int = MAX_ATTEMPTS_PER_BATCH_SIZE,
    state=None,   # optional GenerationState — populated when provided
) -> dict | None:
    """
    Generate quiz questions in batches with retry/fallback.

    Returns a quiz dict {'quiz_title': ..., 'questions': [...]} or None if
    generation failed completely. The returned questions list may be shorter
    than num_questions if errors consumed some of the attempt budget.
    """
    # Deferred imports — prevents env-var check at module import time
    from llm.llm_client import run_prompt
    from llm.quiz_model import Quiz
    from prompt_manager.manager import PromptManager
    from llm.generation_config import QUIZ_SOURCE_CONTEXT_CHARS

    if state is not None:
        from llm.generation_state import record_accepted_batch, record_rejection

    manager = PromptManager()
    accumulated: list[dict] = []
    quiz_title: str | None = None
    locked_size = initial_batch_size
    attempts_at_size = 0
    current_batch = 1          # batch number for state tracking (1-based)
    batch_attempt_count = 0    # attempts on the current (in-progress) batch
    # Safety cap: avoids infinite loops in degenerate configs
    total_cap = (num_questions // max(min_batch_size, 1) + 2) * max_attempts_per_size * 3
    total_attempts = 0

    while len(accumulated) < num_questions and total_attempts < total_cap:
        remaining = num_questions - len(accumulated)
        batch_size = min(locked_size, remaining)
        total_attempts += 1
        batch_attempt_count += 1
        decision: Decision = "halt"

        try:
            built = manager.build_from_template(
                prompt_name="quiz_generation",
                topic=topic,
                difficulty=difficulty,
                num_questions=batch_size,
                source_text=(
                    source_text[:QUIZ_SOURCE_CONTEXT_CHARS]
                    if source_text
                    else "No source text provided."
                ),
            )
            if not built:
                print("[batch] prompt build failed — halting")
                break

            result = run_prompt(built["system"], built["user"], Quiz)
            questions = result.get("questions", [])

            if not questions:
                decision = "reduce"
            else:
                if quiz_title is None:
                    quiz_title = result.get("quiz_title", f"Quiz: {topic}")
                if state is not None:
                    record_accepted_batch(state, current_batch, batch_size, len(questions), batch_attempt_count)
                accumulated.extend(questions)
                current_batch += 1
                batch_attempt_count = 0
                attempts_at_size = 0
                print(f"[batch] accepted {len(questions)}q — total {len(accumulated)}/{num_questions}")
                continue

        except Exception as exc:
            decision = classify_exception(exc)
            print(f"[batch] {type(exc).__name__} → {decision}")
            if state is not None:
                record_rejection(state, current_batch, batch_attempt_count, batch_size, decision, type(exc).__name__)

        # Handle non-accept outcomes
        attempts_at_size += 1
        if decision == "halt":
            break
        if should_reduce(decision, attempts_at_size, max_attempts_per_size):
            new_size = reduce_batch_size(locked_size, fallback_batch_size, min_batch_size)
            if new_size < locked_size:
                print(f"[batch] reducing {locked_size} → {new_size}")
                locked_size = new_size
                attempts_at_size = 0
            else:
                print("[batch] already at minimum batch size — halting")
                break
        # else: "retry" → loop continues with same locked_size

    if state is not None:
        state["final_locked_batch_size"] = locked_size

    if not accumulated:
        return None

    return {
        "quiz_title": quiz_title or f"Quiz: {topic}",
        "questions": accumulated[:num_questions],
    }
