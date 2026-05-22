"""
Background generation worker for quiz partial loading.

Runs quiz generation in a background thread. Partial results become
available as batches complete via the on_partial_ready callback from
batch_strategy.run_batched_generation().

Usage:
    worker = BackgroundGenerationWorker("Python", "easy", 20)
    worker.start()

    # In a UI polling loop:
    snapshot = worker.get_snapshot()
    if snapshot.partial_result:
        display(snapshot.partial_result.questions)
    if snapshot.is_done:
        finalise(snapshot.partial_result)
"""
from __future__ import annotations
import threading
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from llm.partial_loading import PartialResult


# ── Worker lifecycle status ───────────────────────────────────────────────────

class WorkerStatus(str, Enum):
    """Worker thread lifecycle status. Separate from GenerationStatus in partial_loading."""
    IDLE    = "idle"
    RUNNING = "running"
    DONE    = "done"


@dataclass
class WorkerSnapshot:
    """Immutable, thread-safe snapshot of worker state at a point in time."""
    worker_status: WorkerStatus
    partial_result: PartialResult | None  # latest result, or None if none yet
    is_done: bool                    # True when thread has exited
    error: str | None                # set if the worker thread raised an exception


class BackgroundGenerationWorker:
    """
    Runs run_batched_generation in a background thread.

    Thread communication:
    - _on_partial_ready() is called by the batch runner after each accepted batch.
    - get_snapshot() reads the latest result under a lock.

    _run_function is an injection point for testing: it receives the
    on_partial_ready callback and calls it as results arrive, without
    requiring a live API.
    """

    def __init__(
        self,
        topic: str,
        difficulty: str,
        num_questions: int,
        source_text: str | None = None,
        source_slices: list[tuple[str, int]] | None = None,
        _run_function: Callable | None = None,
    ) -> None:
        # source_slices: RAG per-slice mode — list of (source_text, n_questions).
        # When set, each slice drives one run_batched_generation call.
        # source_text is used as the single context in non-RAG mode.
        self._topic          = topic
        self._difficulty     = difficulty
        self._num_questions  = num_questions
        self._source_text    = source_text
        self._source_slices  = source_slices
        self._run_function   = _run_function   # None → real generation

        self._lock           = threading.Lock()
        self._thread: threading.Thread | None = None
        self._worker_status  = WorkerStatus.IDLE
        self._latest_partial = None
        self._error: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch background generation. Non-blocking — returns immediately."""
        with self._lock:
            if self._worker_status != WorkerStatus.IDLE:
                return
            self._worker_status = WorkerStatus.RUNNING

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get_snapshot(self) -> WorkerSnapshot:
        """Return a thread-safe immutable snapshot of the current state."""
        with self._lock:
            return WorkerSnapshot(
                worker_status=self._worker_status,
                partial_result=self._latest_partial,
                is_done=(self._worker_status == WorkerStatus.DONE),
                error=self._error,
            )

    def is_done(self) -> bool:
        """Return True when the background thread has exited."""
        with self._lock:
            return self._worker_status == WorkerStatus.DONE

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_partial_ready(self, partial_result) -> None:
        """Called by the batch runner on each accepted batch."""
        with self._lock:
            self._latest_partial = partial_result

    def _run(self) -> None:
        """Background thread entry point."""
        try:
            if self._run_function is not None:
                self._run_function(self._on_partial_ready)
            elif self._source_slices:
                self._real_run_slices()
            else:
                self._real_run()
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
        finally:
            with self._lock:
                self._worker_status = WorkerStatus.DONE

    def _real_run(self) -> None:
        """Single source_text generation path. All imports deferred to avoid env-var errors at load time."""
        from llm.batch_strategy import run_batched_generation
        from llm.generation_state import create_state
        from llm.generation_config import (
            INITIAL_BATCH_SIZE, FALLBACK_BATCH_SIZE,
            MIN_BATCH_SIZE, MAX_ATTEMPTS_PER_BATCH_SIZE,
        )
        from llm.partial_loading import build_final_result
        from llm.answer_shuffle import shuffle_quiz_options_balanced

        state = create_state(
            self._topic, self._difficulty, self._num_questions, INITIAL_BATCH_SIZE
        )

        quiz_json = run_batched_generation(
            self._topic, self._difficulty, self._num_questions, self._source_text,
            initial_batch_size=INITIAL_BATCH_SIZE,
            fallback_batch_size=FALLBACK_BATCH_SIZE,
            min_batch_size=MIN_BATCH_SIZE,
            max_attempts_per_size=MAX_ATTEMPTS_PER_BATCH_SIZE,
            state=state,
            on_partial_ready=self._on_partial_ready,
        )

        # Final structural validation — same safety net as _post_process_quiz() in generate_quiz().
        # Batches are already Pydantic-validated at parse time, so failure here is extremely
        # unlikely but would indicate corruption introduced after batch assembly.
        if quiz_json:
            from pydantic import ValidationError
            from llm.quiz_model import Quiz
            try:
                Quiz.model_validate(quiz_json)
            except ValidationError as exc:
                print(f"[validation] final quiz failed model_validate: {exc}")

        # Apply balanced shuffle to the final quiz before surfacing it to the UI.
        # Intermediate partial results (per-batch callbacks) are left unshuffled
        # to avoid visible question reordering during streaming.
        if quiz_json:
            quiz_json = shuffle_quiz_options_balanced(quiz_json)

        questions  = quiz_json.get("questions", []) if quiz_json else []
        quiz_title = quiz_json.get("quiz_title")    if quiz_json else None
        final = build_final_result(questions, quiz_title, state)

        with self._lock:
            self._latest_partial = final

    def _real_run_slices(self) -> None:
        """RAG per-slice generation path.

        Each (source_text, n_questions) slice drives one run_batched_generation call.
        The shared GenerationState accumulates accepted_questions across all slices so
        that partial results show the growing total. After each completed slice the
        latest partial is published for live UI updates between slices.
        Retry/reduce operates independently per slice.
        """
        from llm.batch_strategy import run_batched_generation
        from llm.generation_state import create_state
        from llm.generation_config import (
            INITIAL_BATCH_SIZE, FALLBACK_BATCH_SIZE,
            MIN_BATCH_SIZE, MAX_ATTEMPTS_PER_BATCH_SIZE,
        )
        from llm.partial_loading import build_partial_result, build_final_result
        from llm.answer_shuffle import shuffle_quiz_options_balanced

        state = create_state(
            self._topic, self._difficulty, self._num_questions, INITIAL_BATCH_SIZE
        )

        all_questions: list[dict] = []
        quiz_title: str | None = None

        for source_text, n_questions in self._source_slices:
            if n_questions <= 0:
                continue

            slice_quiz = run_batched_generation(
                self._topic, self._difficulty, n_questions, source_text,
                initial_batch_size=INITIAL_BATCH_SIZE,
                fallback_batch_size=FALLBACK_BATCH_SIZE,
                min_batch_size=MIN_BATCH_SIZE,
                max_attempts_per_size=MAX_ATTEMPTS_PER_BATCH_SIZE,
                state=state,
                on_partial_ready=None,
            )

            if slice_quiz:
                if quiz_title is None:
                    quiz_title = slice_quiz.get("quiz_title")
                all_questions.extend(slice_quiz.get("questions", []))
                self._on_partial_ready(
                    build_partial_result(all_questions, quiz_title, state)
                )

        quiz_json = (
            {"quiz_title": quiz_title or f"Quiz: {self._topic}", "questions": all_questions}
            if all_questions else None
        )

        if quiz_json:
            from pydantic import ValidationError
            from llm.quiz_model import Quiz
            try:
                Quiz.model_validate(quiz_json)
            except ValidationError as exc:
                print(f"[validation] final quiz failed model_validate: {exc}")

        if quiz_json:
            quiz_json = shuffle_quiz_options_balanced(quiz_json)

        questions  = quiz_json.get("questions", []) if quiz_json else []
        quiz_title = quiz_json.get("quiz_title")    if quiz_json else None
        final = build_final_result(questions, quiz_title, state)

        with self._lock:
            self._latest_partial = final
