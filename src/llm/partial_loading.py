"""
Partial loading state and flow for quiz generation.

Defines generation status values, the PartialResult type, and pure functions
for deriving and building partial results from a GenerationState.

This module is a state/flow layer — it does not start threads or background
tasks. Background execution is the responsibility of background_generation_worker.

Status progression (synchronous path):
  (initial) → COMPLETED | HALTED | FAILED

Status progression (with background worker — future):
  RUNNING → PARTIAL → COMPLETED | HALTED | FAILED
"""
from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING, Callable, TypedDict

if TYPE_CHECKING:
    from llm.generation_state import GenerationState


# ── Generation status ─────────────────────────────────────────────────────────

class GenerationStatus(str, Enum):
    """Generation lifecycle status. Inherits str so values compare equal to string literals."""
    RUNNING   = "running"    # worker started, no questions yet
    PARTIAL   = "partial"    # first batch available, worker still running
    COMPLETED = "completed"  # all requested questions generated
    HALTED    = "halted"     # some questions generated, stopped early
    FAILED    = "failed"     # zero questions generated


# Statuses that indicate generation will not continue
FINAL_STATUSES: frozenset[GenerationStatus] = frozenset({
    GenerationStatus.COMPLETED,
    GenerationStatus.HALTED,
    GenerationStatus.FAILED,
})


# ── Result type ───────────────────────────────────────────────────────────────

class PartialResult(TypedDict):
    status: str
    questions: list[dict]
    accepted_count: int
    requested_count: int
    missing_count: int
    quiz_title: str | None
    is_final: bool   # True when status is one of FINAL_STATUSES


# Callback type for partial result availability notifications
PartialReadyCallback = Callable[[PartialResult], None]


# ── Status helpers ────────────────────────────────────────────────────────────

def determine_final_status(state: "GenerationState") -> GenerationStatus:
    """
    Derive the terminal generation status from a completed GenerationState.
    Call this after generation has fully stopped (success or failure).
    """
    accepted  = state["accepted_questions"]
    requested = state["requested_questions"]
    if accepted == 0:
        return GenerationStatus.FAILED
    if accepted >= requested:
        return GenerationStatus.COMPLETED
    return GenerationStatus.HALTED


def should_return_partial(state: "GenerationState", min_questions: int = 1) -> bool:
    """Return True when at least min_questions are available to show."""
    return state["accepted_questions"] >= min_questions


# ── Result builders ───────────────────────────────────────────────────────────

def build_partial_result(
    questions: list[dict],
    quiz_title: str | None,
    state: "GenerationState",
    is_final: bool = False,
) -> PartialResult:
    """
    Build a PartialResult snapshot from the current generation state.

    When is_final=False the status reflects mid-generation progress.
    When is_final=True the status is the terminal status derived from state.
    """
    accepted  = state["accepted_questions"]
    requested = state["requested_questions"]

    if is_final:
        status = determine_final_status(state)
    else:
        status = GenerationStatus.PARTIAL if accepted > 0 else GenerationStatus.RUNNING

    return PartialResult(
        status=status,
        questions=list(questions),   # snapshot — not a reference
        accepted_count=accepted,
        requested_count=requested,
        missing_count=max(0, requested - accepted),
        quiz_title=quiz_title,
        is_final=is_final,
    )


def build_final_result(
    questions: list[dict],
    quiz_title: str | None,
    state: "GenerationState",
) -> PartialResult:
    """Convenience wrapper: build_partial_result with is_final=True."""
    return build_partial_result(questions, quiz_title, state, is_final=True)
