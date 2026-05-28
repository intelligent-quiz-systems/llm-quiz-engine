"""
Batch retry/fallback strategy for quiz generation.

Generates quiz questions in multiple API calls, reducing batch size
on failures and retrying according to the configured limits.

Reduction sequence: 10 → 5 → 3 → 2 → 1 → 1 → 1 → halt
  - Quality errors and output errors cause immediate reduction (no retry).
  - Transient API errors ("retry") allow up to MAX_ATTEMPTS_PER_BATCH_SIZE
    retries before reducing.
  - batch_size=1 allows MAX_SINGLE_ATTEMPTS consecutive fails before halt.

Error classification here is intentionally lightweight — it maps exceptions
to control-flow decisions (reduce/retry/halt) only. For full diagnostic
logging of error details, see the diagnostics/provider-error-details branch.
"""
from __future__ import annotations
import time
from typing import Literal

import openai

# Decision type for batch control flow
Decision = Literal["accept", "retry", "reduce", "halt"]

# Module-level defaults — match generation_config.py values.
# Defined here so this module can be imported without triggering llm/__init__.py.
INITIAL_BATCH_SIZE          : int   = 10
FALLBACK_BATCH_SIZE         : int   = 5
MIN_BATCH_SIZE              : int   = 1
MAX_ATTEMPTS_PER_BATCH_SIZE : int   = 2
BATCH_SIZE_STEPS            : tuple = (10, 5, 3, 2, 1)
MAX_SINGLE_ATTEMPTS         : int   = 3


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
    steps: tuple = BATCH_SIZE_STEPS,
) -> int:
    """
    Return the next smaller batch size from the reduction sequence.

    Scans BATCH_SIZE_STEPS for the first value smaller than current.
    Returns the minimum step if current is already at or below it.
    """
    for step in steps:
        if step < current:
            return step
    return steps[-1]


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
    batch_size_steps: tuple = BATCH_SIZE_STEPS,
    max_single_attempts: int = MAX_SINGLE_ATTEMPTS,
    previous_questions: list[str] | None = None,
    cross_slice_accumulated: list[dict] | None = None,
    state=None,             # optional GenerationState — populated when provided
    on_partial_ready=None,  # optional PartialReadyCallback — called after each accepted batch
    source_text_limit: int | None = None,  # chars to pass to prompt; None → QUIZ_SOURCE_CONTEXT_CHARS
) -> dict | None:
    """
    Generate quiz questions in batches with retry/fallback.

    Reduction sequence: initial → ... → 1 → 1 → 1 → halt
    Each quality error or output error causes immediate batch size reduction.
    Transient errors allow up to max_attempts_per_size retries before reducing.
    At batch_size=1, max_single_attempts consecutive fails trigger a halt.

    cross_slice_accumulated: questions accepted by previous source slices.
    When set, the quality gate checks new batches against both within-slice
    accumulated questions AND these cross-slice questions, so duplicate and
    similarity detection operates globally across the whole quiz.

    Returns a quiz dict {'quiz_title': ..., 'questions': [...]} or None if
    generation failed completely. The returned questions list may be shorter
    than num_questions if errors consumed some of the attempt budget.
    """
    # Deferred imports — prevents env-var check at module import time
    from llm.llm_client import run_prompt
    from llm.quiz_model import Quiz
    from prompt_manager.manager import PromptManager
    from llm.generation_config import QUIZ_SOURCE_CONTEXT_CHARS, GUARDRAIL_MAX_QUESTIONS
    _source_limit = source_text_limit if source_text_limit is not None else QUIZ_SOURCE_CONTEXT_CHARS
    from llm.guardrail import build_guardrail_context
    from llm.question_quality import run_per_batch_gate, format_quality_log

    if state is not None:
        from llm.generation_state import record_accepted_batch, record_rejection

    manager = PromptManager()
    accumulated: list[dict] = []
    quiz_title: str | None = None
    locked_size = initial_batch_size
    attempts_at_size = 0
    single_question_attempts = 0   # consecutive fails at batch_size=1
    current_batch = 1              # batch number for state tracking (1-based)
    batch_attempt_count = 0        # attempts on the current (in-progress) batch

    # Dead-loop safety guard only — not a primary control mechanism.
    # Normal flow halts via single_question_attempts long before this cap.
    total_cap = num_questions * 4 + 30
    total_attempts = 0

    while len(accumulated) < num_questions and total_attempts < total_cap:
        remaining = num_questions - len(accumulated)
        batch_size = min(locked_size, remaining)
        total_attempts += 1
        batch_attempt_count += 1
        decision: Decision = "halt"

        # Per-attempt diagnostic accumulators (reset each iteration)
        _s_chars = 0
        _u_chars = 0
        _g_q_count = 0
        _g_chars = 0
        _attempt_start = time.monotonic()

        try:
            accumulated_texts = [q.get("question", "") for q in accumulated if q.get("question")]
            all_prior = list(previous_questions or []) + accumulated_texts
            use_guardrail = bool(all_prior)
            if use_guardrail:
                guardrail_ctx = build_guardrail_context(all_prior, max_questions=GUARDRAIL_MAX_QUESTIONS)
                guardrail_text = guardrail_ctx["text"]
                _g_q_count = guardrail_ctx.get("question_count", 0)
                _g_chars = guardrail_ctx.get("chars", 0)
            else:
                guardrail_text = ""

            built = manager.build_from_template(
                prompt_name="quiz_generation",
                version="v2" if use_guardrail else None,
                topic=topic,
                difficulty=difficulty,
                num_questions=batch_size,
                source_text=(
                    source_text[:_source_limit]
                    if source_text
                    else "No source text provided."
                ),
                guardrail=guardrail_text,
            )
            if not built:
                print("[batch] prompt build failed - halting")
                break

            _s_chars = len(built["system"])
            _u_chars = len(built["user"])

            raw = run_prompt(built["system"], built["user"], Quiz, include_metadata=True)
            _attempt_dur = round(time.monotonic() - _attempt_start, 3)

            questions = raw["quiz"].get("questions", [])

            if not questions:
                decision = "reduce"
            else:
                # ── Hard quality gate ────────────────────────────────────────
                effective_accumulated = accumulated + (cross_slice_accumulated or [])
                gate_issues = run_per_batch_gate(questions, effective_accumulated)
                hard_issues = [iss for iss in gate_issues if iss["severity"] == "error"]
                if gate_issues:
                    print(format_quality_log(gate_issues))
                if hard_issues:
                    print(
                        f"[batch] quality gate rejected {len(hard_issues)} error(s) "
                        f"— reducing batch size"
                    )
                    decision = "reduce"
                    if state is not None:
                        record_rejection(
                            state, current_batch, batch_attempt_count, batch_size, "reduce",
                            "QualityGateReject",
                            attempt_duration_seconds=_attempt_dur,
                            system_prompt_chars=_s_chars,
                            user_prompt_chars=_u_chars,
                            total_prompt_chars=_s_chars + _u_chars,
                            guardrail_question_count=_g_q_count,
                            guardrail_chars=_g_chars,
                        )
                    # Fall through to the reduce logic below
                else:
                    # ── Accept batch ─────────────────────────────────────────
                    if quiz_title is None:
                        quiz_title = raw["quiz"].get("quiz_title", f"Quiz: {topic}")
                    if state is not None:
                        record_accepted_batch(
                            state, current_batch, batch_size, len(questions), batch_attempt_count,
                            attempt_duration_seconds=_attempt_dur,
                            batch_duration_seconds=_attempt_dur,
                            input_tokens=raw.get("input_tokens"),
                            output_tokens=raw.get("output_tokens"),
                            reasoning_tokens=raw.get("reasoning_tokens"),
                            total_tokens=raw.get("total_tokens"),
                            system_prompt_chars=_s_chars,
                            user_prompt_chars=_u_chars,
                            total_prompt_chars=_s_chars + _u_chars,
                            guardrail_question_count=_g_q_count,
                            guardrail_chars=_g_chars,
                        )
                    accumulated.extend(questions)
                    current_batch += 1
                    batch_attempt_count = 0
                    attempts_at_size = 0
                    single_question_attempts = 0
                    print(f"[batch] accepted {len(questions)}q - total {len(accumulated)}/{num_questions}")
                    if on_partial_ready is not None and state is not None:
                        from llm.partial_loading import build_partial_result, should_return_partial
                        if should_return_partial(state):
                            on_partial_ready(build_partial_result(accumulated, quiz_title, state))
                    continue

        except Exception as exc:
            _attempt_dur = round(time.monotonic() - _attempt_start, 3)
            decision = classify_exception(exc)
            print(f"[batch] {type(exc).__name__} -> {decision}")
            from llm.provider_errors import classify_provider_error, format_error_log
            print(format_error_log(classify_provider_error(exc)))
            if state is not None:
                record_rejection(
                    state, current_batch, batch_attempt_count, batch_size, decision, type(exc).__name__,
                    attempt_duration_seconds=_attempt_dur,
                    system_prompt_chars=_s_chars,
                    user_prompt_chars=_u_chars,
                    total_prompt_chars=_s_chars + _u_chars,
                    guardrail_question_count=_g_q_count,
                    guardrail_chars=_g_chars,
                )

        # ── Handle non-accept outcomes ────────────────────────────────────────
        attempts_at_size += 1

        if decision == "halt":
            break

        # Track consecutive fails at batch_size=1
        if locked_size == 1:
            single_question_attempts += 1
            if single_question_attempts >= max_single_attempts:
                print(
                    f"[batch] {max_single_attempts} consecutive fails at batch_size=1 - halting"
                )
                break

        if should_reduce(decision, attempts_at_size, max_attempts_per_size):
            new_size = reduce_batch_size(locked_size, batch_size_steps)
            if new_size < locked_size:
                print(f"[batch] reducing {locked_size} -> {new_size}")
                locked_size = new_size
                attempts_at_size = 0
                if locked_size > 1:
                    single_question_attempts = 0
            else:
                print("[batch] already at minimum batch size - halting")
                break
        # else: "retry" within budget → loop continues with same locked_size

    if state is not None:
        state["final_locked_batch_size"] = locked_size

    if not accumulated:
        return None

    return {
        "quiz_title": quiz_title or f"Quiz: {topic}",
        "questions": accumulated[:num_questions],
    }
