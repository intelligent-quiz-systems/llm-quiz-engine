"""
Tests for generation state, batch log, and rejection log helpers.
No API access required — all functions are pure state mutations.

Run with pytest or directly:  python src/tests/test_generation_state.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from generation_state import (
    create_state,
    record_accepted_batch,
    record_rejection,
    format_state_summary,
)


# ── create_state ──────────────────────────────────────────────────────────────

def test_initial_values():
    s = create_state("Python", "easy", 20, 10)
    assert s["topic"] == "Python"
    assert s["difficulty"] == "easy"
    assert s["requested_questions"] == 20
    assert s["accepted_questions"] == 0
    assert s["total_batches"] == 0
    assert s["rejected_attempts"] == 0
    assert s["initial_batch_size"] == 10
    assert s["final_locked_batch_size"] == 10
    assert s["batch_log"] == []
    assert s["rejection_log"] == []


# ── record_accepted_batch ─────────────────────────────────────────────────────

def test_accepted_batch_increments_counts():
    s = create_state("Python", "easy", 20, 10)
    record_accepted_batch(s, batch_number=1, batch_size=10, questions_accepted=10, attempts=1)
    assert s["total_batches"] == 1
    assert s["accepted_questions"] == 10
    assert len(s["batch_log"]) == 1


def test_accepted_batch_log_entry_fields():
    s = create_state("Python", "easy", 20, 10)
    record_accepted_batch(s, batch_number=1, batch_size=10, questions_accepted=10, attempts=2)
    entry = s["batch_log"][0]
    assert entry["batch_number"] == 1
    assert entry["accepted_batch_size"] == 10
    assert entry["accepted_questions"] == 10
    assert entry["total_attempts"] == 2
    assert entry["outcome"] == "accepted"


def test_multiple_batches_accumulate():
    s = create_state("Python", "easy", 20, 10)
    record_accepted_batch(s, 1, 10, 10, 1)
    record_accepted_batch(s, 2, 5, 5, 3)   # second batch with fallback size
    assert s["total_batches"] == 2
    assert s["accepted_questions"] == 15
    assert len(s["batch_log"]) == 2


# ── record_rejection ──────────────────────────────────────────────────────────

def test_rejection_increments_counter():
    s = create_state("Python", "easy", 20, 10)
    record_rejection(s, batch_number=1, attempt_number=1, batch_size=10,
                     decision="reduce", error_type="BadRequestError")
    assert s["rejected_attempts"] == 1
    assert len(s["rejection_log"]) == 1


def test_rejection_log_entry_fields():
    s = create_state("Python", "easy", 20, 10)
    record_rejection(s, batch_number=1, attempt_number=2, batch_size=5,
                     decision="retry", error_type="APITimeoutError")
    entry = s["rejection_log"][0]
    assert entry["batch_number"] == 1
    assert entry["attempt_number"] == 2
    assert entry["attempted_batch_size"] == 5
    assert entry["decision"] == "retry"
    assert entry["error_type"] == "APITimeoutError"


def test_multiple_rejections_accumulate():
    s = create_state("Python", "easy", 20, 10)
    record_rejection(s, 1, 1, 10, "reduce", "BadRequestError")
    record_rejection(s, 1, 2, 5,  "reduce", "LengthFinishReasonError")
    record_rejection(s, 2, 1, 5,  "retry",  "APITimeoutError")
    assert s["rejected_attempts"] == 3
    assert len(s["rejection_log"]) == 3


# ── combined scenario ─────────────────────────────────────────────────────────

def test_mixed_accepts_and_rejections():
    s = create_state("History", "hard", 15, 10)
    record_rejection(s, 1, 1, 10, "reduce", "BadRequestError")
    record_accepted_batch(s, 1, 5, 5, 2)
    record_accepted_batch(s, 2, 5, 5, 1)
    record_rejection(s, 3, 1, 5, "halt", "RateLimitError")
    assert s["total_batches"] == 2
    assert s["accepted_questions"] == 10
    assert s["rejected_attempts"] == 2


# ── format_state_summary ──────────────────────────────────────────────────────

def test_summary_contains_key_fields():
    s = create_state("Python", "easy", 20, 10)
    record_accepted_batch(s, 1, 10, 10, 1)
    log = format_state_summary(s)
    assert "===== GENERATION SUMMARY =====" in log
    assert "Python" in log
    assert "20" in log  # requested
    assert "10" in log  # accepted


def test_summary_shows_rejection_breakdown_when_rejections_exist():
    s = create_state("Python", "easy", 20, 10)
    record_rejection(s, 1, 1, 10, "reduce", "BadRequestError")
    log = format_state_summary(s)
    assert "rejection_decisions" in log
    assert "rejection_errors" in log


def test_summary_no_rejection_section_when_clean():
    s = create_state("Python", "easy", 10, 10)
    record_accepted_batch(s, 1, 10, 10, 1)
    log = format_state_summary(s)
    assert "rejection_decisions" not in log


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
