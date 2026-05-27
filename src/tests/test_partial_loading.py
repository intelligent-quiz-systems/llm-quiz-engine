"""
Tests for partial loading state and flow helpers.
No API access required — all functions are pure transformations.

Run with pytest or directly:  python src/tests/test_partial_loading.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from generation_state import create_state, record_accepted_batch, record_rejection
from partial_loading import (
    GenerationStatus,
    FINAL_STATUSES,
    determine_final_status,
    should_return_partial,
    build_partial_result,
    build_final_result,
    PartialResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _state(requested: int = 20, accepted: int = 0) -> dict:
    s = create_state("Python", "easy", requested, 10)
    s["accepted_questions"] = accepted
    return s


def _questions(n: int) -> list[dict]:
    return [{"question": f"Q{i}?", "options": ["A", "B", "C", "D"], "correct_index": 0}
            for i in range(n)]


# ── determine_final_status ────────────────────────────────────────────────────

def test_final_status_completed():
    s = _state(requested=10, accepted=10)
    assert determine_final_status(s) == GenerationStatus.COMPLETED


def test_final_status_completed_overshoot():
    s = _state(requested=10, accepted=12)  # rare but possible
    assert determine_final_status(s) == GenerationStatus.COMPLETED


def test_final_status_halted_when_partial():
    s = _state(requested=20, accepted=10)
    assert determine_final_status(s) == GenerationStatus.HALTED


def test_final_status_failed_when_zero():
    s = _state(requested=20, accepted=0)
    assert determine_final_status(s) == GenerationStatus.FAILED


# ── should_return_partial ─────────────────────────────────────────────────────

def test_should_return_partial_when_enough():
    s = _state(accepted=5)
    assert should_return_partial(s, min_questions=1) is True
    assert should_return_partial(s, min_questions=5) is True


def test_should_not_return_partial_when_empty():
    s = _state(accepted=0)
    assert should_return_partial(s, min_questions=1) is False


def test_should_not_return_partial_below_min():
    s = _state(accepted=3)
    assert should_return_partial(s, min_questions=5) is False


# ── build_partial_result (is_final=False) ────────────────────────────────────

def test_partial_result_mid_generation_status():
    s = _state(requested=20, accepted=10)
    questions = _questions(10)
    result = build_partial_result(questions, "My Quiz", s, is_final=False)
    assert result["status"] == GenerationStatus.PARTIAL
    assert result["is_final"] is False


def test_partial_result_running_status_when_no_questions():
    s = _state(requested=20, accepted=0)
    result = build_partial_result([], None, s, is_final=False)
    assert result["status"] == GenerationStatus.RUNNING
    assert result["is_final"] is False


def test_partial_result_counts():
    s = _state(requested=20, accepted=10)
    result = build_partial_result(_questions(10), "T", s)
    assert result["accepted_count"] == 10
    assert result["requested_count"] == 20
    assert result["missing_count"] == 10


def test_partial_result_zero_missing_when_complete():
    s = _state(requested=10, accepted=10)
    result = build_partial_result(_questions(10), "T", s)
    assert result["missing_count"] == 0


def test_partial_result_quiz_title():
    s = _state(requested=10, accepted=5)
    result = build_partial_result([], "My Quiz Title", s)
    assert result["quiz_title"] == "My Quiz Title"


def test_partial_result_questions_are_snapshot():
    s = _state(requested=10, accepted=3)
    qs = _questions(3)
    result = build_partial_result(qs, None, s)
    # Mutation of original list does not affect result
    qs.append({"question": "extra", "options": [], "correct_index": 0})
    assert len(result["questions"]) == 3


# ── build_final_result ────────────────────────────────────────────────────────

def test_final_result_completed():
    s = _state(requested=10, accepted=10)
    result = build_final_result(_questions(10), "T", s)
    assert result["status"] == GenerationStatus.COMPLETED
    assert result["is_final"] is True


def test_final_result_halted():
    s = _state(requested=20, accepted=8)
    result = build_final_result(_questions(8), "T", s)
    assert result["status"] == GenerationStatus.HALTED
    assert result["is_final"] is True


def test_final_result_failed():
    s = _state(requested=20, accepted=0)
    result = build_final_result([], None, s)
    assert result["status"] == GenerationStatus.FAILED
    assert result["is_final"] is True


# ── FINAL_STATUSES set ────────────────────────────────────────────────────────

def test_final_statuses_contains_terminal_values():
    assert GenerationStatus.COMPLETED in FINAL_STATUSES
    assert GenerationStatus.HALTED    in FINAL_STATUSES
    assert GenerationStatus.FAILED    in FINAL_STATUSES


def test_in_progress_statuses_not_final():
    assert GenerationStatus.RUNNING not in FINAL_STATUSES
    assert GenerationStatus.PARTIAL not in FINAL_STATUSES


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
