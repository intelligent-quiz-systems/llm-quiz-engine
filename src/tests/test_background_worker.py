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
    WORKER_IDLE,
    WORKER_RUNNING,
    WORKER_DONE,
)
from generation_state import create_state, record_accepted_batch
from partial_loading import (
    build_partial_result,
    build_final_result,
    STATUS_PARTIAL,
    STATUS_COMPLETED,
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
    assert w.get_snapshot().worker_status == WORKER_IDLE


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
    assert snap.worker_status in (WORKER_RUNNING, WORKER_DONE)
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
    # Give the finally block time to set WORKER_DONE
    time.sleep(0.05)

    assert w.is_done() is True
    snap = w.get_snapshot()
    assert snap.partial_result is not None
    assert snap.error is None
    assert snap.worker_status == WORKER_DONE


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
    assert snap.partial_result["status"] == STATUS_COMPLETED


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
    assert snap.is_done == (snap.worker_status == WORKER_DONE)


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
