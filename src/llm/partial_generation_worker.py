import copy
import threading
import time
import uuid

from llm.llm2 import build_quiz_from_state, generate_next_quiz_chunk

_WORKERS_LOCK = threading.Lock()
# PL: Zakończone workery nie są usuwane ze słownika — świadome uproszczenie MVP.
# PL: Temat ewentualnego cleanupu zostawiamy na później.
# EN: Finished workers are never removed from this dict — deliberate MVP simplification.
# EN: Cleanup is left for a later decision.
_WORKERS: dict[str, dict] = {}

DEBUG_PARTIAL_GENERATION_WORKER = True


def debug_worker(event: str, **payload) -> None:
    if not DEBUG_PARTIAL_GENERATION_WORKER:
        return

    print(f"\n===== PARTIAL GENERATION WORKER: {event} =====")
    for key, value in payload.items():
        print(f"{key}: {value}")


def _safe_quiz_from_state(topic: str, state: dict | None) -> dict | None:
    if not isinstance(state, dict):
        return None

    try:
        return build_quiz_from_state(state, fallback_title=topic)
    except Exception:
        return None


def _get_worker_unlocked(worker_id: str) -> dict | None:
    return _WORKERS.get(worker_id)


def _finalize_worker_unlocked(worker: dict, *, completed: bool, failed: bool, error: str | None) -> None:
    now = time.time()
    worker["completed"] = completed
    worker["failed"] = failed
    worker["running"] = False
    worker["last_error"] = error
    worker["finished_at"] = now

    started_at = worker.get("started_at")
    if started_at is not None:
        worker["duration_seconds"] = max(0.0, now - started_at)
    else:
        worker["duration_seconds"] = None


def _worker_loop(worker_id: str) -> None:
    with _WORKERS_LOCK:
        worker = _get_worker_unlocked(worker_id)
        if worker is None:
            return

        worker["running"] = True
        worker["started_at"] = time.time()

        topic = worker["topic"]
        difficulty = worker["difficulty"]

    debug_worker(
        "WORKER STARTED",
        worker_id=worker_id,
        topic=topic,
        difficulty=difficulty,
    )

    while True:
        with _WORKERS_LOCK:
            worker = _get_worker_unlocked(worker_id)
            if worker is None:
                return

            if worker.get("stop_requested"):
                # PL: Worker sprawdza flagę dopiero po zakończeniu bieżącego wywołania LLM.
                # PL: Zatrzymanie nie jest natychmiastowe — to normalne zachowanie.
                # EN: The worker checks this flag only after the current LLM call finishes.
                # EN: Stop is not immediate — this is expected behavior.
                _finalize_worker_unlocked(
                    worker,
                    completed=False,
                    failed=False,
                    error="worker stopped by request",
                )
                debug_worker(
                    "WORKER STOP REQUESTED",
                    worker_id=worker_id,
                )
                return

            state_for_chunk = copy.deepcopy(worker["state"])
            topic = worker["topic"]
            difficulty = worker["difficulty"]

        if state_for_chunk.get("completed"):
            with _WORKERS_LOCK:
                worker = _get_worker_unlocked(worker_id)
                if worker is None:
                    return

                worker["state"] = copy.deepcopy(state_for_chunk)
                worker["quiz"] = _safe_quiz_from_state(topic, state_for_chunk)
                _finalize_worker_unlocked(
                    worker,
                    completed=True,
                    failed=False,
                    error=None,
                )

            debug_worker(
                "WORKER EXIT - ALREADY COMPLETED",
                worker_id=worker_id,
            )
            return

        if state_for_chunk.get("failed"):
            with _WORKERS_LOCK:
                worker = _get_worker_unlocked(worker_id)
                if worker is None:
                    return

                worker["state"] = copy.deepcopy(state_for_chunk)
                worker["quiz"] = _safe_quiz_from_state(topic, state_for_chunk)
                _finalize_worker_unlocked(
                    worker,
                    completed=False,
                    failed=True,
                    error=state_for_chunk.get("last_error"),
                )

            debug_worker(
                "WORKER EXIT - ALREADY FAILED",
                worker_id=worker_id,
                error=state_for_chunk.get("last_error"),
            )
            return

        result = generate_next_quiz_chunk(topic, difficulty, state_for_chunk)

        result_state = result.get("state")
        if not isinstance(result_state, dict):
            result_state = state_for_chunk

        result_quiz = result.get("quiz")
        if not isinstance(result_quiz, dict):
            result_quiz = _safe_quiz_from_state(topic, result_state)

        with _WORKERS_LOCK:
            worker = _get_worker_unlocked(worker_id)
            if worker is None:
                return

            worker["state"] = copy.deepcopy(result_state)
            worker["quiz"] = copy.deepcopy(result_quiz)
            worker["last_result"] = copy.deepcopy(result)
            worker["last_error"] = result.get("error")
            worker["updated_at"] = time.time()

            if result.get("completed"):
                _finalize_worker_unlocked(
                    worker,
                    completed=True,
                    failed=False,
                    error=None,
                )

            elif result.get("failed"):
                _finalize_worker_unlocked(
                    worker,
                    completed=False,
                    failed=True,
                    error=result.get("error"),
                )

        debug_worker(
            "WORKER STEP",
            worker_id=worker_id,
            result_ok=result.get("ok"),
            result_completed=result.get("completed"),
            result_failed=result.get("failed"),
            state_questions=len(result_state.get("accepted_questions", [])),
            error=result.get("error"),
        )

        if result.get("completed") or result.get("failed"):
            return


def start_generation_worker(
    topic: str,
    difficulty: str,
    initial_state: dict,
) -> str:
    worker_id = uuid.uuid4().hex

    worker_record = {
        "worker_id": worker_id,
        "topic": topic,
        "difficulty": difficulty,
        "state": copy.deepcopy(initial_state),
        "quiz": _safe_quiz_from_state(topic, initial_state),
        "last_result": None,
        "last_error": None,
        "running": False,
        "completed": False,
        "failed": False,
        "stop_requested": False,
        "created_at": time.time(),
        "started_at": None,
        "updated_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "thread": None,
    }

    thread = threading.Thread(
        target=_worker_loop,
        args=(worker_id,),
        daemon=True,
        name=f"partial-generation-worker-{worker_id[:8]}",
    )
    worker_record["thread"] = thread

    with _WORKERS_LOCK:
        _WORKERS[worker_id] = worker_record

    debug_worker(
        "WORKER REGISTERED",
        worker_id=worker_id,
        topic=topic,
        difficulty=difficulty,
        initial_state_questions=len(initial_state.get("accepted_questions", [])),
    )

    thread.start()
    return worker_id


def get_generation_worker_snapshot(worker_id: str) -> dict | None:
    with _WORKERS_LOCK:
        worker = _get_worker_unlocked(worker_id)
        if worker is None:
            return None

        thread = worker.get("thread")
        return {
            "worker_id": worker["worker_id"],
            "topic": worker["topic"],
            "difficulty": worker["difficulty"],
            "state": copy.deepcopy(worker["state"]),
            "quiz": copy.deepcopy(worker["quiz"]),
            "last_result": copy.deepcopy(worker["last_result"]),
            "last_error": worker["last_error"],
            "running": worker["running"],
            "completed": worker["completed"],
            "failed": worker["failed"],
            "stop_requested": worker["stop_requested"],
            "created_at": worker["created_at"],
            "started_at": worker["started_at"],
            "updated_at": worker["updated_at"],
            "finished_at": worker["finished_at"],
            "duration_seconds": worker["duration_seconds"],
            "thread_alive": thread.is_alive() if thread else False,
        }


def stop_generation_worker(worker_id: str) -> None:
    with _WORKERS_LOCK:
        worker = _get_worker_unlocked(worker_id)
        if worker is None:
            return

        worker["stop_requested"] = True

    debug_worker(
        "WORKER MARKED TO STOP",
        worker_id=worker_id,
    )