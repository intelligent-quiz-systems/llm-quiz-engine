import copy
import re
import time

import streamlit as st

from llm.llm2 import build_quiz_from_state, start_partial_quiz_generation
from llm.partial_generation_worker import (
    get_generation_worker_snapshot,
    start_generation_worker,
    stop_generation_worker,
)
from validations.validate_quiz import validate_quiz

PARTIAL_GENERATION_RETRY_DELAY_SECONDS = 1.5
LONG_PROVIDER_WAIT_THRESHOLD_SECONDS = 60.0
DEBUG_PARTIAL_LOADING = True


def map_difficulty_to_en(difficulty_value) -> str:
    difficulty_pl = str(difficulty_value)

    difficulty_map = {
        "Łatwy": "easy",
        "Średni": "medium",
        "Trudny": "hard",
    }

    return difficulty_map.get(difficulty_pl, difficulty_pl)


def clear_question_widget_keys() -> None:
    keys_to_remove = [
        key
        for key in st.session_state.keys()
        if key.startswith("widget_q_")
    ]
    for key in keys_to_remove:
        del st.session_state[key]


def ensure_partial_generation_defaults() -> None:
    defaults = {
        "generation_state": None,
        "partial_generation_error": None,
        "partial_generation_in_progress": False,
        "partial_generation_in_progress_since": 0.0,
        "partial_generation_halted": False,
        "partial_generation_next_attempt_at": 0.0,
        "partial_generation_last_generation_id": None,
        "partial_generation_worker_id": None,
        "generation_started_at": None,
        "generation_finished_at": None,
        "generation_duration_seconds": None,
        "generation_average_seconds_per_question": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_partial_generation_session() -> None:
    worker_id = st.session_state.get("partial_generation_worker_id")
    if worker_id:
        stop_generation_worker(worker_id)

    st.session_state.generation_state = None
    st.session_state.partial_generation_error = None
    st.session_state.partial_generation_in_progress = False
    st.session_state.partial_generation_in_progress_since = 0.0
    st.session_state.partial_generation_halted = False
    st.session_state.partial_generation_next_attempt_at = 0.0
    st.session_state.partial_generation_last_generation_id = None
    st.session_state.partial_generation_worker_id = None
    st.session_state.generation_started_at = None
    st.session_state.generation_finished_at = None
    st.session_state.generation_duration_seconds = None
    st.session_state.generation_average_seconds_per_question = None


def attach_quiz_metadata(quiz: dict, config: dict) -> dict:
    enriched_quiz = quiz.copy()
    enriched_quiz["topic"] = config.get("topic")
    enriched_quiz["difficulty"] = config.get("difficulty")
    enriched_quiz["time_limit"] = config.get("time_limit")
    enriched_quiz["question_count"] = config.get("question_count")
    return enriched_quiz


def validate_or_raise(quiz: dict | None) -> None:
    is_valid, error_message = validate_quiz(quiz)
    if not is_valid:
        raise ValueError(f"Niepoprawny format quizu: {error_message}")


def build_generation_id(config: dict) -> str:
    timestamp_ms = int(time.time() * 1000)
    topic = str(config.get("topic", "")).strip()
    difficulty = str(config.get("difficulty", "")).strip()
    question_count = config.get("question_count", "")
    return f"{topic}|{difficulty}|{question_count}|{timestamp_ms}"


def extract_provider_wait_seconds(error_message: str | None) -> float | None:
    if not error_message:
        return None

    minutes_seconds_match = re.search(
        r"try again in\s*([0-9]+)m([0-9]+(?:\.[0-9]+)?)s",
        error_message,
        flags=re.IGNORECASE,
    )
    if minutes_seconds_match:
        try:
            minutes = float(minutes_seconds_match.group(1))
            seconds = float(minutes_seconds_match.group(2))
            return (minutes * 60.0) + seconds
        except ValueError:
            return None

    seconds_match = re.search(
        r"try again in\s*([0-9]+(?:\.[0-9]+)?)s",
        error_message,
        flags=re.IGNORECASE,
    )
    if seconds_match:
        try:
            return float(seconds_match.group(1))
        except ValueError:
            return None

    return None


def should_halt_partial_generation(error_message: str | None) -> bool:
    # PL: Przy TPD albo bardzo długim czasie oczekiwania zatrzymujemy automatyczne dogrywanie.
    # EN: For TPD or a very long wait time, we stop automatic background loading.
    if not error_message:
        return False

    lowered = error_message.lower()

    if "tokens per day" in lowered:
        return True

    if "tpd" in lowered:
        return True

    wait_seconds = extract_provider_wait_seconds(error_message)
    if wait_seconds is not None and wait_seconds >= LONG_PROVIDER_WAIT_THRESHOLD_SECONDS:
        return True

    return False


def get_quiz_question_count(quiz: dict | None) -> int:
    if not isinstance(quiz, dict):
        return 0

    questions = quiz.get("questions", [])
    if not isinstance(questions, list):
        return 0

    return len(questions)


def get_state_question_count(state: dict | None) -> int:
    if not isinstance(state, dict):
        return 0

    accepted_questions = state.get("accepted_questions")
    if isinstance(accepted_questions, list):
        return len(accepted_questions)

    for key in ("generated_questions", "accepted_total", "question_count"):
        value = state.get(key)
        if isinstance(value, int):
            return value

    return 0


def debug_partial_loading(event: str, **payload) -> None:
    if not DEBUG_PARTIAL_LOADING:
        return

    print(f"\n===== PARTIAL LOADING DEBUG: {event} =====")
    for key, value in payload.items():
        print(f"{key}: {value}")


def build_quiz_from_generation_state(
    state: dict | None,
    config: dict,
    fallback_title: str | None = None,
) -> dict | None:
    if not isinstance(state, dict):
        return None

    title_fallback = fallback_title or str(config.get("topic") or "Quiz")
    raw_quiz = build_quiz_from_state(state, fallback_title=title_fallback)
    validate_or_raise(raw_quiz)

    quiz = attach_quiz_metadata(raw_quiz, config)
    quiz["questions"] = quiz.get("questions", [])[: config["question_count"]]
    return quiz


def sync_quiz_data_from_state_if_needed(config: dict) -> bool:
    state = st.session_state.get("generation_state")
    quiz = st.session_state.get("quiz_data")

    state_questions = get_state_question_count(state)
    quiz_questions = get_quiz_question_count(quiz)

    if state_questions <= quiz_questions:
        return False

    synced_quiz = build_quiz_from_generation_state(
        state,
        config,
        fallback_title=str(config.get("topic") or "Quiz"),
    )
    if synced_quiz is None:
        return False

    st.session_state.quiz_data = synced_quiz

    debug_partial_loading(
        "SYNC QUIZ DATA FROM STATE",
        previous_quiz_questions=quiz_questions,
        synced_quiz_questions=get_quiz_question_count(synced_quiz),
        state_questions=state_questions,
    )
    return True


def sync_session_from_worker_snapshot(config: dict, snapshot: dict) -> None:
    snapshot_state = snapshot.get("state")
    snapshot_quiz = snapshot.get("quiz")

    if isinstance(snapshot_state, dict):
        st.session_state.generation_state = copy.deepcopy(snapshot_state)

    current_quiz = st.session_state.get("quiz_data")
    current_quiz_questions = get_quiz_question_count(current_quiz)
    snapshot_quiz_questions = get_quiz_question_count(snapshot_quiz)
    snapshot_state_questions = get_state_question_count(snapshot_state)

    if snapshot_quiz_questions > current_quiz_questions:
        updated_quiz = attach_quiz_metadata(copy.deepcopy(snapshot_quiz), config)
        updated_quiz["questions"] = updated_quiz.get("questions", [])[: config["question_count"]]
        st.session_state.quiz_data = updated_quiz

        debug_partial_loading(
            "SYNC SESSION FROM WORKER QUIZ",
            previous_quiz_questions=current_quiz_questions,
            worker_quiz_questions=snapshot_quiz_questions,
            worker_state_questions=snapshot_state_questions,
        )
        return

    if snapshot_state_questions > current_quiz_questions:
        sync_quiz_data_from_state_if_needed(config)


def start_generation_timing() -> None:
    started_at = time.time()
    st.session_state.generation_started_at = started_at
    st.session_state.generation_finished_at = None
    st.session_state.generation_duration_seconds = None
    st.session_state.generation_average_seconds_per_question = None

    debug_partial_loading(
        "GENERATION TIMING STARTED",
        generation_started_at=started_at,
    )


def finalize_generation_timing_if_needed(config: dict) -> bool:
    started_at = st.session_state.get("generation_started_at")
    finished_at = st.session_state.get("generation_finished_at")

    if started_at is None:
        return False

    if finished_at is not None:
        return False

    now = time.time()
    duration_seconds = max(0.0, now - started_at)
    target_questions = config.get("question_count", 0)

    average_seconds_per_question = None
    if isinstance(target_questions, int) and target_questions > 0:
        average_seconds_per_question = duration_seconds / target_questions

    st.session_state.generation_finished_at = now
    st.session_state.generation_duration_seconds = duration_seconds
    st.session_state.generation_average_seconds_per_question = average_seconds_per_question

    debug_partial_loading(
        "GENERATION TIMING FINISHED",
        generation_started_at=started_at,
        generation_finished_at=now,
        generation_duration_seconds=round(duration_seconds, 3),
        average_seconds_per_question=(
            round(average_seconds_per_question, 3)
            if average_seconds_per_question is not None
            else None
        ),
        target_questions=target_questions,
    )
    return True


def get_generation_timing_summary(config: dict | None = None) -> dict:
    started_at = st.session_state.get("generation_started_at")
    finished_at = st.session_state.get("generation_finished_at")
    duration_seconds = st.session_state.get("generation_duration_seconds")
    average_seconds_per_question = st.session_state.get("generation_average_seconds_per_question")

    quiz = st.session_state.get("quiz_data")
    ready_questions = get_quiz_question_count(quiz)

    target_questions = ready_questions
    if config and isinstance(config.get("question_count"), int):
        target_questions = config["question_count"]

    status = "not_started"
    if started_at is not None and finished_at is None:
        status = "running"
    elif started_at is not None and finished_at is not None:
        status = "completed"

    return {
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "average_seconds_per_question": average_seconds_per_question,
        "ready_questions": ready_questions,
        "target_questions": target_questions,
    }


def get_partial_loading_status() -> tuple[str, str] | None:
    config = st.session_state.get("config")
    quiz = st.session_state.get("quiz_data")
    state = st.session_state.get("generation_state")
    error_message = st.session_state.get("partial_generation_error")

    if not config or not quiz:
        return None

    ready_questions = len(quiz.get("questions", []))
    target_questions = config.get("question_count", ready_questions)

    if error_message:
        return (
            "warning",
            (
                f"Dogrywanie kolejnych pytań zatrzymało się. "
                f"Gotowe pytania: {ready_questions}/{target_questions}. "
                f"Szczegóły: {error_message}"
            ),
        )

    if not state:
        return None

    if state.get("completed"):
        return (
            "success",
            f"Quiz gotowy. Wczytano wszystkie pytania: {ready_questions}/{target_questions}.",
        )

    return (
        "info",
        f"Quiz dogrywa się partiami. Gotowe pytania: {ready_questions}/{target_questions}.",
    )


def start_partial_quiz_flow(config: dict) -> None:
    difficulty_en = map_difficulty_to_en(config["difficulty"])
    generation_id = build_generation_id(config)

    start_generation_timing()

    debug_partial_loading(
        "START FLOW - BEFORE INITIAL CALL",
        topic=config.get("topic"),
        difficulty=difficulty_en,
        requested_questions=config.get("question_count"),
        generation_id=generation_id,
    )

    partial_result = start_partial_quiz_generation(
        config["topic"],
        difficulty_en,
        config["question_count"],
    )

    if not partial_result["ok"]:
        error_message = (
            partial_result.get("error")
            or "Nie udało się rozpocząć generowania quizu."
        )
        raise ValueError(error_message)

    raw_quiz = partial_result.get("quiz")
    validate_or_raise(raw_quiz)

    quiz = attach_quiz_metadata(raw_quiz, config)
    quiz["questions"] = quiz.get("questions", [])[: config["question_count"]]

    st.session_state.quiz_data = quiz
    st.session_state.generation_state = partial_result.get("state")
    st.session_state.current_page = 0
    st.session_state.app_step = "quiz"
    st.session_state.config = config
    st.session_state.quiz_deadline = None
    st.session_state.answers = {}
    st.session_state.timeout_happened = False
    st.session_state.partial_generation_error = None
    st.session_state.partial_generation_in_progress = False
    st.session_state.partial_generation_in_progress_since = 0.0
    st.session_state.partial_generation_halted = bool(partial_result.get("completed"))
    st.session_state.partial_generation_next_attempt_at = 0.0
    st.session_state.partial_generation_last_generation_id = generation_id
    st.session_state.partial_generation_worker_id = None

    if partial_result.get("completed"):
        finalize_generation_timing_if_needed(config)
    else:
        worker_id = start_generation_worker(
            topic=config["topic"],
            difficulty=difficulty_en,
            initial_state=partial_result["state"],
        )
        st.session_state.partial_generation_worker_id = worker_id

        debug_partial_loading(
            "BACKGROUND WORKER STARTED",
            worker_id=worker_id,
            initial_quiz_questions=get_quiz_question_count(quiz),
            initial_state_questions=get_state_question_count(partial_result.get("state")),
        )

    debug_partial_loading(
        "START FLOW - AFTER INITIAL CALL",
        initial_quiz_questions=get_quiz_question_count(quiz),
        initial_state_questions=get_state_question_count(partial_result.get("state")),
        completed=partial_result.get("completed"),
        halted=st.session_state.partial_generation_halted,
        generation_id=st.session_state.partial_generation_last_generation_id,
    )

    clear_question_widget_keys()


def continue_partial_quiz_flow() -> None:
    config = st.session_state.get("config")
    quiz = st.session_state.get("quiz_data")
    state = st.session_state.get("generation_state")

    if not config or not quiz or not state:
        debug_partial_loading(
            "CONTINUE EXIT - MISSING DATA",
            has_config=bool(config),
            has_quiz=bool(quiz),
            has_state=bool(state),
        )
        return

    worker_id = st.session_state.get("partial_generation_worker_id")

    if not worker_id:
        sync_quiz_data_from_state_if_needed(config)

        state = st.session_state.get("generation_state")
        if isinstance(state, dict) and state.get("completed"):
            finalize_generation_timing_if_needed(config)

            if not st.session_state.get("partial_generation_halted", False):
                debug_partial_loading(
                    "CONTINUE EXIT - NO WORKER, STATE COMPLETED",
                    quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                    state_questions=get_state_question_count(state),
                )

            st.session_state.partial_generation_halted = True
            return

        if isinstance(state, dict) and state.get("failed"):
            st.session_state.partial_generation_error = state.get("last_error")

            if not st.session_state.get("partial_generation_halted", False):
                debug_partial_loading(
                    "CONTINUE EXIT - NO WORKER, STATE FAILED",
                    quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                    state_questions=get_state_question_count(state),
                    error=state.get("last_error"),
                )

            st.session_state.partial_generation_halted = True
            return

        return

    snapshot = get_generation_worker_snapshot(worker_id)
    if snapshot is None:
        debug_partial_loading(
            "CONTINUE EXIT - WORKER SNAPSHOT MISSING",
            worker_id=worker_id,
        )
        return

    sync_session_from_worker_snapshot(config, snapshot)

    snapshot_error = snapshot.get("last_error")
    if snapshot_error and snapshot.get("failed"):
        st.session_state.partial_generation_error = snapshot_error
        st.session_state.partial_generation_halted = True
        st.session_state.partial_generation_worker_id = None

        debug_partial_loading(
            "CONTINUE EXIT - WORKER FAILED",
            worker_id=worker_id,
            error=snapshot_error,
            quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions=get_state_question_count(st.session_state.get("generation_state")),
        )
        return

    if snapshot.get("completed"):
        finalize_generation_timing_if_needed(config)
        st.session_state.partial_generation_halted = True
        st.session_state.partial_generation_worker_id = None

        debug_partial_loading(
            "CONTINUE EXIT - WORKER COMPLETED",
            worker_id=worker_id,
            quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions=get_state_question_count(st.session_state.get("generation_state")),
        )
        return

    debug_partial_loading(
        "CONTINUE POLL - WORKER RUNNING",
        worker_id=worker_id,
        worker_running=snapshot.get("running"),
        worker_thread_alive=snapshot.get("thread_alive"),
        quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
        state_questions=get_state_question_count(st.session_state.get("generation_state")),
    )