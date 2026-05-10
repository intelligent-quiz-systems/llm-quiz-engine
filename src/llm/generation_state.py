"""
Generation state, batch log, and rejection log for quiz generation runs.

Tracks what happened during a batched generation: how many questions were
accepted, how many attempts were rejected and why, batch size changes, etc.
Designed to feed reports and diagnostics — does not affect generation logic.
"""
from __future__ import annotations
from typing import TypedDict


class RejectionLogEntry(TypedDict):
    batch_number: int           # batch we were attempting (1-based)
    attempt_number: int         # attempt within this batch (1-based)
    attempted_batch_size: int
    decision: str               # "reduce" | "retry" | "halt"
    error_type: str             # exception class name
    attempt_duration_seconds: float | None
    provider_error_info: dict | None
    system_prompt_chars: int
    user_prompt_chars: int
    total_prompt_chars: int


class BatchLogEntry(TypedDict):
    batch_number: int
    accepted_batch_size: int    # size of the call that was accepted
    accepted_questions: int
    total_attempts: int         # includes failed attempts for this batch
    outcome: str                # "accepted"
    attempt_duration_seconds: float | None
    batch_duration_seconds: float | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    system_prompt_chars: int
    user_prompt_chars: int
    total_prompt_chars: int


class GenerationState(TypedDict):
    topic: str
    difficulty: str
    requested_questions: int
    accepted_questions: int
    total_batches: int          # number of accepted batches
    rejected_attempts: int      # total failed attempts across all batches
    initial_batch_size: int
    final_locked_batch_size: int
    batch_log: list[BatchLogEntry]
    rejection_log: list[RejectionLogEntry]


# ── Factory ───────────────────────────────────────────────────────────────────

def create_state(
    topic: str,
    difficulty: str,
    num_questions: int,
    initial_batch_size: int,
) -> GenerationState:
    return GenerationState(
        topic=topic,
        difficulty=difficulty,
        requested_questions=num_questions,
        accepted_questions=0,
        total_batches=0,
        rejected_attempts=0,
        initial_batch_size=initial_batch_size,
        final_locked_batch_size=initial_batch_size,
        batch_log=[],
        rejection_log=[],
    )


# ── Mutation helpers ──────────────────────────────────────────────────────────

def record_accepted_batch(
    state: GenerationState,
    batch_number: int,
    batch_size: int,
    questions_accepted: int,
    attempts: int,
    *,
    attempt_duration_seconds: float | None = None,
    batch_duration_seconds: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    total_tokens: int | None = None,
    system_prompt_chars: int = 0,
    user_prompt_chars: int = 0,
    total_prompt_chars: int = 0,
) -> None:
    state["total_batches"] += 1
    state["accepted_questions"] += questions_accepted
    state["batch_log"].append(BatchLogEntry(
        batch_number=batch_number,
        accepted_batch_size=batch_size,
        accepted_questions=questions_accepted,
        total_attempts=attempts,
        outcome="accepted",
        attempt_duration_seconds=attempt_duration_seconds,
        batch_duration_seconds=batch_duration_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        system_prompt_chars=system_prompt_chars,
        user_prompt_chars=user_prompt_chars,
        total_prompt_chars=total_prompt_chars,
    ))


def record_rejection(
    state: GenerationState,
    batch_number: int,
    attempt_number: int,
    batch_size: int,
    decision: str,
    error_type: str,
    *,
    attempt_duration_seconds: float | None = None,
    provider_error_info: dict | None = None,
    system_prompt_chars: int = 0,
    user_prompt_chars: int = 0,
    total_prompt_chars: int = 0,
) -> None:
    state["rejected_attempts"] += 1
    state["rejection_log"].append(RejectionLogEntry(
        batch_number=batch_number,
        attempt_number=attempt_number,
        attempted_batch_size=batch_size,
        decision=decision,
        error_type=error_type,
        attempt_duration_seconds=attempt_duration_seconds,
        provider_error_info=provider_error_info,
        system_prompt_chars=system_prompt_chars,
        user_prompt_chars=user_prompt_chars,
        total_prompt_chars=total_prompt_chars,
    ))


# ── Log formatter ─────────────────────────────────────────────────────────────

def format_state_summary(state: GenerationState) -> str:
    """Return a structured log block for stdout."""
    lines = [
        "\n===== GENERATION SUMMARY =====",
        f"topic:                {state['topic']}",
        f"difficulty:           {state['difficulty']}",
        f"requested_questions:  {state['requested_questions']}",
        f"accepted_questions:   {state['accepted_questions']}",
        f"total_batches:        {state['total_batches']}",
        f"rejected_attempts:    {state['rejected_attempts']}",
        f"initial_batch_size:   {state['initial_batch_size']}",
        f"final_batch_size:     {state['final_locked_batch_size']}",
    ]
    if state["rejection_log"]:
        from collections import Counter
        decisions = Counter(e["decision"] for e in state["rejection_log"])
        errors    = Counter(e["error_type"] for e in state["rejection_log"])
        lines.append(f"rejection_decisions:  {dict(decisions)}")
        lines.append(f"rejection_errors:     {dict(errors)}")
    return "\n".join(lines)
