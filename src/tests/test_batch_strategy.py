"""
Tests for batch retry/fallback strategy helpers.
No API access required — only pure decision functions are tested here.

run_batched_generation() requires a live API and is not tested directly;
it is covered by integration tests when API access is available.

Run with pytest or directly:  python src/tests/test_batch_strategy.py
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from batch_strategy import (
    classify_exception,
    reduce_batch_size,
    should_reduce,
    INITIAL_BATCH_SIZE,
    FALLBACK_BATCH_SIZE,
    MIN_BATCH_SIZE,
    MAX_ATTEMPTS_PER_BATCH_SIZE,
    BATCH_SIZE_STEPS,
    MAX_SINGLE_ATTEMPTS,
)


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 400) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.request = MagicMock()
    r.headers = MagicMock()
    r.headers.get = MagicMock(return_value=None)
    return r


# ── classify_exception ────────────────────────────────────────────────────────

def test_rate_limit_halts():
    exc = openai.RateLimitError("rl", response=_mock_response(429), body=None)
    assert classify_exception(exc) == "halt"


def test_bad_request_reduces():
    exc = openai.BadRequestError("br", response=_mock_response(400), body=None)
    assert classify_exception(exc) == "reduce"


def test_length_finish_reduces():
    exc = openai.LengthFinishReasonError(completion=MagicMock())
    assert classify_exception(exc) == "reduce"


def test_timeout_retries():
    exc = openai.APITimeoutError(request=MagicMock())
    assert classify_exception(exc) == "retry"


def test_connection_error_retries():
    exc = openai.APIConnectionError(request=MagicMock())
    assert classify_exception(exc) == "retry"


def test_content_filter_halts():
    exc = openai.ContentFilterFinishReasonError()
    assert classify_exception(exc) == "halt"


def test_unknown_exception_halts():
    assert classify_exception(ValueError("unexpected")) == "halt"
    assert classify_exception(RuntimeError("other")) == "halt"


# ── reduce_batch_size — new sequence-based implementation ─────────────────────

def test_full_reduction_sequence():
    """Verify the complete 10 → 5 → 3 → 2 → 1 sequence."""
    assert reduce_batch_size(10) == 5
    assert reduce_batch_size(5)  == 3
    assert reduce_batch_size(3)  == 2
    assert reduce_batch_size(2)  == 1
    assert reduce_batch_size(1)  == 1  # already at minimum — stays


def test_reduces_from_initial():
    result = reduce_batch_size(INITIAL_BATCH_SIZE)
    assert result < INITIAL_BATCH_SIZE
    assert result == 5  # first step in BATCH_SIZE_STEPS below 10


def test_stays_at_minimum():
    assert reduce_batch_size(MIN_BATCH_SIZE) == MIN_BATCH_SIZE


def test_custom_steps_sequence():
    steps = (10, 5, 2)
    assert reduce_batch_size(10, steps) == 5
    assert reduce_batch_size(5,  steps) == 2
    assert reduce_batch_size(2,  steps) == 2   # already at minimum
    assert reduce_batch_size(1,  steps) == 2   # below all steps → returns last


def test_cannot_go_below_step_minimum():
    steps = (10, 5, 1)
    assert reduce_batch_size(1, steps) == 1


def test_batch_size_steps_constant_is_ordered():
    """BATCH_SIZE_STEPS must be strictly decreasing."""
    for i in range(len(BATCH_SIZE_STEPS) - 1):
        assert BATCH_SIZE_STEPS[i] > BATCH_SIZE_STEPS[i + 1], (
            f"BATCH_SIZE_STEPS not strictly decreasing at index {i}"
        )


def test_batch_size_steps_starts_with_initial():
    assert BATCH_SIZE_STEPS[0] == INITIAL_BATCH_SIZE


def test_batch_size_steps_ends_with_minimum():
    assert BATCH_SIZE_STEPS[-1] == MIN_BATCH_SIZE


def test_fallback_present_in_steps():
    assert FALLBACK_BATCH_SIZE in BATCH_SIZE_STEPS


def test_intermediate_steps_present():
    """3 and 2 must exist between 5 and 1."""
    assert 3 in BATCH_SIZE_STEPS
    assert 2 in BATCH_SIZE_STEPS


# ── should_reduce ─────────────────────────────────────────────────────────────

def test_reduce_decision_triggers_immediately():
    assert should_reduce("reduce", 0, MAX_ATTEMPTS_PER_BATCH_SIZE) is True


def test_retry_exhausted_triggers_reduce():
    max_a = MAX_ATTEMPTS_PER_BATCH_SIZE
    assert should_reduce("retry", max_a, max_a) is True


def test_retry_below_limit_does_not_reduce():
    assert should_reduce("retry", 1, MAX_ATTEMPTS_PER_BATCH_SIZE) is False


def test_halt_does_not_trigger_reduce():
    assert should_reduce("halt", 0, MAX_ATTEMPTS_PER_BATCH_SIZE) is False
    assert should_reduce("halt", 99, MAX_ATTEMPTS_PER_BATCH_SIZE) is False


# ── MAX_SINGLE_ATTEMPTS ───────────────────────────────────────────────────────

def test_max_single_attempts_is_three():
    assert MAX_SINGLE_ATTEMPTS == 3


def test_max_single_attempts_positive():
    assert MAX_SINGLE_ATTEMPTS >= 1


# ── constant sanity ───────────────────────────────────────────────────────────

def test_batch_size_ordering():
    assert INITIAL_BATCH_SIZE > FALLBACK_BATCH_SIZE > MIN_BATCH_SIZE >= 1


def test_max_attempts_positive():
    assert MAX_ATTEMPTS_PER_BATCH_SIZE >= 1


# ── cross_slice_accumulated parameter ────────────────────────────────────────

def test_cross_slice_accumulated_param_has_none_default():
    import inspect
    from batch_strategy import run_batched_generation
    sig = inspect.signature(run_batched_generation)
    param = sig.parameters.get("cross_slice_accumulated")
    assert param is not None, "cross_slice_accumulated param missing from run_batched_generation"
    assert param.default is None


def test_cross_slice_accumulated_is_keyword_only():
    import inspect
    from batch_strategy import run_batched_generation
    sig = inspect.signature(run_batched_generation)
    param = sig.parameters["cross_slice_accumulated"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed.")
