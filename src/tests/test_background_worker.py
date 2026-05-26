"""
Tests for the background generation worker.
No API access required — real generation is replaced by injected run functions.

Run with pytest or directly:  python src/tests/test_background_worker.py
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from background_worker import (
    BackgroundGenerationWorker,
    WorkerSnapshot,
    WorkerStatus,
)
from generation_state import create_state, record_accepted_batch
from partial_loading import (
    build_partial_result,
    build_final_result,
    GenerationStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _questions(n: int) -> list[dict]:
    return [{"question": f"Q{i}?", "options": ["A", "B", "C", "D"], "correct_index": 0}
            for i in range(n)]


def _make_partial(accepted: int = 5, requested: int = 10) -> dict:
    s = create_state("Python", "easy", requested, 10)
    record_accepted_batch(s, 1, accepted, accepted, 1)
    return build_partial_result(_questions(accepted), "Test Quiz", s)


def _make_final(accepted: int = 10, requested: int = 10) -> dict:
    s = create_state("Python", "easy", requested, 10)
    record_accepted_batch(s, 1, accepted, accepted, 1)
    return build_final_result(_questions(accepted), "Test Quiz", s)


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_worker_status_is_idle():
    w = BackgroundGenerationWorker("Python", "easy", 10)
    assert w.get_snapshot().worker_status == WorkerStatus.IDLE


def test_initial_is_done_false():
    w = BackgroundGenerationWorker("Python", "easy", 10)
    assert w.is_done() is False


def test_initial_partial_result_is_none():
    w = BackgroundGenerationWorker("Python", "easy", 10)
    assert w.get_snapshot().partial_result is None


def test_initial_error_is_none():
    w = BackgroundGenerationWorker("Python", "easy", 10)
    assert w.get_snapshot().error is None


def test_initial_snapshot_is_not_done():
    w = BackgroundGenerationWorker("Python", "easy", 10)
    assert w.get_snapshot().is_done is False


# ── start() ───────────────────────────────────────────────────────────────────

def test_start_changes_status_to_running_or_done():
    done = threading.Event()

    def fast_run(callback):
        done.wait()  # block until we check running status

    w = BackgroundGenerationWorker("Python", "easy", 5, _run_function=fast_run)
    w.start()
    snap = w.get_snapshot()
    # Status should be RUNNING (thread blocked in fast_run) or DONE (race)
    assert snap.worker_status in (WorkerStatus.RUNNING, WorkerStatus.DONE)
    done.set()  # release the thread


def test_double_start_is_idempotent():
    done = threading.Event()
    call_count = [0]

    def run(callback):
        call_count[0] += 1
        done.set()

    w = BackgroundGenerationWorker("Python", "easy", 5, _run_function=run)
    w.start()
    w.start()  # second call should be a no-op
    done.wait(timeout=2.0)
    assert call_count[0] == 1


# ── Completed run with injected function ──────────────────────────────────────

def test_worker_calls_on_partial_ready_and_completes():
    done = threading.Event()
    received = []

    def run(on_partial_ready):
        partial = _make_partial(accepted=5, requested=10)
        on_partial_ready(partial)
        received.append(partial)
        done.set()

    w = BackgroundGenerationWorker("Python", "easy", 10, _run_function=run)
    w.start()
    done.wait(timeout=2.0)
    # Give the finally block time to set WorkerStatus.DONE
    time.sleep(0.05)

    assert w.is_done() is True
    snap = w.get_snapshot()
    assert snap.partial_result is not None
    assert snap.error is None
    assert snap.worker_status == WorkerStatus.DONE


def test_worker_final_partial_result_accessible():
    done = threading.Event()

    def run(on_partial_ready):
        final = _make_final(accepted=10, requested=10)
        on_partial_ready(final)
        done.set()

    w = BackgroundGenerationWorker("Python", "easy", 10, _run_function=run)
    w.start()
    done.wait(timeout=2.0)
    time.sleep(0.05)

    snap = w.get_snapshot()
    assert snap.partial_result["status"] == GenerationStatus.COMPLETED


def test_worker_multiple_partials_last_wins():
    done = threading.Event()

    def run(on_partial_ready):
        on_partial_ready(_make_partial(accepted=5, requested=20))
        on_partial_ready(_make_partial(accepted=10, requested=20))
        on_partial_ready(_make_partial(accepted=15, requested=20))
        done.set()

    w = BackgroundGenerationWorker("Python", "easy", 20, _run_function=run)
    w.start()
    done.wait(timeout=2.0)
    time.sleep(0.05)

    snap = w.get_snapshot()
    # Last partial had accepted=15
    assert snap.partial_result["accepted_count"] == 15


# ── Error handling ────────────────────────────────────────────────────────────

def test_worker_captures_exception():
    done = threading.Event()

    def failing_run(callback):
        done.set()
        raise RuntimeError("simulated failure")

    w = BackgroundGenerationWorker("Python", "easy", 5, _run_function=failing_run)
    w.start()
    done.wait(timeout=2.0)
    time.sleep(0.05)

    snap = w.get_snapshot()
    assert snap.is_done is True
    assert snap.error is not None
    assert "simulated failure" in snap.error


def test_worker_done_even_after_exception():
    done = threading.Event()

    def run(cb):
        done.set()
        raise ValueError("oops")

    w = BackgroundGenerationWorker("Test", "easy", 5, _run_function=run)
    w.start()
    done.wait(timeout=2.0)
    time.sleep(0.05)
    assert w.is_done() is True


# ── WorkerSnapshot structure ──────────────────────────────────────────────────

def test_snapshot_is_done_matches_worker_status():
    w = BackgroundGenerationWorker("Python", "easy", 5)
    snap = w.get_snapshot()
    assert snap.is_done == (snap.worker_status == WorkerStatus.DONE)


# ── source_slices parameter ───────────────────────────────────────────────────

def test_source_slices_stored_on_init():
    slices = [("ctx1", 3), ("ctx2", 3)]
    w = BackgroundGenerationWorker("Python", "easy", 6, source_slices=slices)
    assert w._source_slices == slices
    assert w._source_text is None


def test_source_slices_alongside_source_text():
    slices = [("ctx1", 5)]
    w = BackgroundGenerationWorker("Python", "easy", 5,
                                   source_text="ignored_when_slices_set",
                                   source_slices=slices)
    assert w._source_slices == slices
    assert w._source_text == "ignored_when_slices_set"


# ── cross-slice quality gate ──────────────────────────────────────────────────

def _ensure_llm_package_importable():
    """Insert src/ before src/llm/ in sys.path so 'llm' resolves as a package.

    test_background_worker.py inserts src/llm/ at position 0, which makes
    'import llm' find llm.py (a file) instead of the llm/ package. Inserting
    src/ first fixes this for tests that need to patch llm.batch_strategy.
    """
    _src = str(Path(__file__).resolve().parents[2] / "src")
    if not sys.path or sys.path[0] != _src:
        sys.path.insert(0, _src)


def test_real_run_slices_passes_growing_cross_slice_context():
    """
    _real_run_slices must pass all previously accepted questions to each
    subsequent slice as both previous_questions (guardrail) and
    cross_slice_accumulated (quality gate), so duplicate/similarity detection
    covers the whole quiz, not just a single slice.
    """
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    recorded = []

    def fake_run_batched(topic, difficulty, n_q, source_text, *,
                         previous_questions=None,
                         cross_slice_accumulated=None, **kw):
        recorded.append({
            "n_prev":  len(previous_questions or []),
            "n_cross": len(cross_slice_accumulated or []),
        })
        return {
            "quiz_title": "T",
            "questions": [
                {"question": f"Q{len(recorded)}_{i}?",
                 "options": ["A", "B", "C", "D"], "correct_index": 0}
                for i in range(n_q)
            ],
        }

    slices = [("ctx1", 2), ("ctx2", 2), ("ctx3", 2)]
    with mock_patch("llm.batch_strategy.run_batched_generation",
                    side_effect=fake_run_batched):
        w = BackgroundGenerationWorker("Python", "easy", 6, source_slices=slices)
        w.start()
        time.sleep(0.5)

    assert w.is_done()
    assert len(recorded) == 3, "expected one run_batched_generation call per slice"

    # Slice 1: no context from previous slices
    assert recorded[0]["n_prev"] == 0
    assert recorded[0]["n_cross"] == 0

    # Slice 2: 2 questions from slice 1
    assert recorded[1]["n_prev"] == 2, (
        "guardrail should contain questions from slice 1"
    )
    assert recorded[1]["n_cross"] == 2, (
        "quality gate should check against slice 1 questions"
    )

    # Slice 3: 4 questions from slices 1 + 2
    assert recorded[2]["n_prev"] == 4, (
        "guardrail should contain questions from slices 1 and 2"
    )
    assert recorded[2]["n_cross"] == 4, (
        "quality gate should check against questions from slices 1 and 2"
    )


def test_real_run_slices_cross_slice_duplicate_would_be_caught():
    """
    Verify that with cross_slice_accumulated set, a slice-2 batch that
    exactly duplicates a slice-1 question arrives at run_per_batch_gate
    with the cross-slice context present. We confirm this by inspecting
    what effective_accumulated would be — the gate logic itself is already
    tested in test_question_quality.py.
    """
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    cross_contexts = []

    def fake_run_batched(topic, difficulty, n_q, source_text, *,
                         cross_slice_accumulated=None, **kw):
        cross_contexts.append(list(cross_slice_accumulated or []))
        return {
            "quiz_title": "T",
            "questions": [
                {"question": f"Q{len(cross_contexts)}?",
                 "options": ["A", "B", "C", "D"], "correct_index": 0}
                for _ in range(n_q)
            ],
        }

    slices = [("ctx1", 1), ("ctx2", 1)]
    with mock_patch("llm.batch_strategy.run_batched_generation",
                    side_effect=fake_run_batched):
        w = BackgroundGenerationWorker("Python", "easy", 2, source_slices=slices)
        w.start()
        time.sleep(0.3)

    assert len(cross_contexts) == 2
    # Slice 1 starts with empty cross-slice context
    assert cross_contexts[0] == []
    # Slice 2 receives slice 1's questions as cross-slice context
    assert len(cross_contexts[1]) == 1
    assert cross_contexts[1][0]["question"] == "Q1?"


# ── get_slice_diagnostics ─────────────────────────────────────────────────────

def test_slice_diagnostics_empty_before_run():
    """get_slice_diagnostics() returns empty list before worker starts."""
    slices = [("ctx1", 2), ("ctx2", 2)]
    w = BackgroundGenerationWorker("Python", "easy", 4, source_slices=slices)
    assert w.get_slice_diagnostics() == []


def test_slice_diagnostics_empty_for_non_rag_mode():
    """Non-RAG mode (_run_function injected) leaves slice diagnostics empty."""
    done = threading.Event()

    def run(cb):
        cb(_make_final(accepted=5, requested=5))
        done.set()

    w = BackgroundGenerationWorker("Python", "easy", 5, _run_function=run)
    w.start()
    done.wait(timeout=2.0)
    time.sleep(0.05)
    assert w.get_slice_diagnostics() == []


def test_slice_diagnostics_count_matches_slices():
    """One diagnostic entry per non-empty source_slice."""
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    def fake_run(topic, difficulty, n_q, source_text, **kw):
        return {
            "quiz_title": "T",
            "questions": [
                {"question": f"Q{i}?", "options": ["A","B","C","D"], "correct_index": 0}
                for i in range(n_q)
            ],
        }

    slices = [("ctx1", 3), ("ctx2", 3), ("ctx3", 4)]
    with mock_patch("llm.batch_strategy.run_batched_generation", side_effect=fake_run):
        w = BackgroundGenerationWorker("Python", "easy", 10, source_slices=slices)
        w.start()
        time.sleep(0.5)

    assert w.is_done()
    diag = w.get_slice_diagnostics()
    assert len(diag) == 3


def test_slice_diagnostics_slice_indices():
    """slice_index is 1-based and sequential."""
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    def fake_run(topic, difficulty, n_q, source_text, **kw):
        return {"quiz_title": "T", "questions": [
            {"question": f"Q?", "options": ["A","B","C","D"], "correct_index": 0}
            for _ in range(n_q)
        ]}

    slices = [("a", 2), ("b", 2)]
    with mock_patch("llm.batch_strategy.run_batched_generation", side_effect=fake_run):
        w = BackgroundGenerationWorker("Python", "easy", 4, source_slices=slices)
        w.start()
        time.sleep(0.4)

    diag = w.get_slice_diagnostics()
    assert diag[0]["slice_index"] == 1
    assert diag[1]["slice_index"] == 2


def test_slice_diagnostics_question_counts_sum():
    """Sum of n_questions_generated across slices equals total questions."""
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    def fake_run(topic, difficulty, n_q, source_text, **kw):
        return {"quiz_title": "T", "questions": [
            {"question": f"Q{i}?", "options": ["A","B","C","D"], "correct_index": 0}
            for i in range(n_q)
        ]}

    slices = [("ctx1", 5), ("ctx2", 3), ("ctx3", 2)]
    with mock_patch("llm.batch_strategy.run_batched_generation", side_effect=fake_run):
        w = BackgroundGenerationWorker("Python", "easy", 10, source_slices=slices)
        w.start()
        time.sleep(0.5)

    diag = w.get_slice_diagnostics()
    total_generated = sum(d["n_questions_generated"] for d in diag)
    assert total_generated == 10


def test_slice_diagnostics_question_texts_match_count():
    """question_texts length matches n_questions_generated for each slice."""
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch

    def fake_run(topic, difficulty, n_q, source_text, **kw):
        return {"quiz_title": "T", "questions": [
            {"question": f"Pytanie {i}?", "options": ["A","B","C","D"], "correct_index": 0}
            for i in range(n_q)
        ]}

    slices = [("ctx1", 4), ("ctx2", 3)]
    with mock_patch("llm.batch_strategy.run_batched_generation", side_effect=fake_run):
        w = BackgroundGenerationWorker("Python", "easy", 7, source_slices=slices)
        w.start()
        time.sleep(0.4)

    diag = w.get_slice_diagnostics()
    for entry in diag:
        assert len(entry["question_texts"]) == entry["n_questions_generated"]
        assert all(isinstance(t, str) for t in entry["question_texts"])


def test_slice_diagnostics_no_cross_contamination():
    """Batch log entries in slice N+1 do not appear in slice N's log."""
    _ensure_llm_package_importable()
    from unittest.mock import patch as mock_patch
    from llm.generation_state import create_state, record_accepted_batch

    call_order = []

    def fake_run(topic, difficulty, n_q, source_text, *, state=None, **kw):
        call_order.append(n_q)
        if state is not None:
            record_accepted_batch(state, len(state["batch_log"]) + 1, n_q, n_q, 1)
        return {"quiz_title": "T", "questions": [
            {"question": f"Q{len(call_order)}_{i}?", "options": ["A","B","C","D"], "correct_index": 0}
            for i in range(n_q)
        ]}

    slices = [("ctx1", 3), ("ctx2", 4)]
    with mock_patch("llm.batch_strategy.run_batched_generation", side_effect=fake_run):
        w = BackgroundGenerationWorker("Python", "easy", 7, source_slices=slices)
        w.start()
        time.sleep(0.5)

    diag = w.get_slice_diagnostics()
    # Each slice should have exactly the batch entries recorded during its own call
    assert len(diag[0]["batch_log"]) == 1
    assert len(diag[1]["batch_log"]) == 1
    # No cross-contamination: slice 1 batch accepted 3q, slice 2 batch accepted 4q
    assert diag[0]["batch_log"][0]["accepted_questions"] == 3
    assert diag[1]["batch_log"][0]["accepted_questions"] == 4


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
