import copy
import re
import time

import streamlit as st

from llm.llm2 import (
    build_quiz_from_state,
    generate_next_quiz_chunk,
    start_partial_quiz_generation,
)
from validations.validate_quiz import validate_quiz

PARTIAL_GENERATION_RETRY_DELAY_SECONDS = 1.5
LONG_PROVIDER_WAIT_THRESHOLD_SECONDS = 60.0
PARTIAL_GENERATION_STALE_LOCK_SECONDS = 15.0
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
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_partial_generation_session() -> None:
    st.session_state.generation_state = None
    st.session_state.partial_generation_error = None
    st.session_state.partial_generation_in_progress = False
    st.session_state.partial_generation_in_progress_since = 0.0
    st.session_state.partial_generation_halted = False
    st.session_state.partial_generation_next_attempt_at = 0.0
    st.session_state.partial_generation_last_generation_id = None


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

    # PL: Jeśli backendowy state jest już dalej niż quiz w UI, nadrabiamy od razu.
    # EN: If backend state is ahead of the UI quiz, sync immediately.
    sync_quiz_data_from_state_if_needed(config)

    quiz = st.session_state.get("quiz_data")
    state = st.session_state.get("generation_state")

    if state.get("completed"):
        sync_quiz_data_from_state_if_needed(config)
        st.session_state.partial_generation_halted = True
        debug_partial_loading(
            "CONTINUE EXIT - STATE COMPLETED",
            quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions=get_state_question_count(st.session_state.get("generation_state")),
            halted=st.session_state.partial_generation_halted,
        )
        return

    if state.get("failed"):
        st.session_state.partial_generation_error = state.get("last_error")
        st.session_state.partial_generation_halted = True
        debug_partial_loading(
            "CONTINUE EXIT - STATE FAILED",
            quiz_questions=get_quiz_question_count(quiz),
            state_questions=get_state_question_count(state),
            error=st.session_state.partial_generation_error,
            halted=st.session_state.partial_generation_halted,
        )
        return

    if st.session_state.get("partial_generation_halted", False):
        debug_partial_loading(
            "CONTINUE EXIT - HALTED FLAG",
            quiz_questions=get_quiz_question_count(quiz),
            state_questions=get_state_question_count(state),
            halted=st.session_state.get("partial_generation_halted"),
        )
        return

    current_generation_id = st.session_state.get("partial_generation_last_generation_id")
    if not current_generation_id:
        debug_partial_loading(
            "CONTINUE EXIT - NO GENERATION ID",
            quiz_questions=get_quiz_question_count(quiz),
            state_questions=get_state_question_count(state),
        )
        return

    now = time.time()
    in_progress = st.session_state.get("partial_generation_in_progress", False)
    in_progress_since = st.session_state.get("partial_generation_in_progress_since", 0.0)
    in_progress_age = now - in_progress_since if in_progress and in_progress_since else 0.0

    if in_progress:
        sync_quiz_data_from_state_if_needed(config)

        if in_progress_age >= PARTIAL_GENERATION_STALE_LOCK_SECONDS:
            st.session_state.partial_generation_in_progress = False
            st.session_state.partial_generation_in_progress_since = 0.0

            debug_partial_loading(
                "CONTINUE RECOVER - STALE IN PROGRESS LOCK",
                stale_lock_seconds=round(in_progress_age, 3),
                quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                state_questions=get_state_question_count(st.session_state.get("generation_state")),
            )
        else:
            debug_partial_loading(
                "CONTINUE EXIT - IN PROGRESS FLAG",
                quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                state_questions=get_state_question_count(st.session_state.get("generation_state")),
                in_progress=True,
                in_progress_age=round(in_progress_age, 3),
            )
            return

    next_attempt_at = st.session_state.get("partial_generation_next_attempt_at", 0.0)
    if now < next_attempt_at:
        debug_partial_loading(
            "CONTINUE EXIT - WAITING FOR RETRY",
            now=now,
            next_attempt_at=next_attempt_at,
            seconds_left=round(next_attempt_at - now, 3),
            quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions=get_state_question_count(st.session_state.get("generation_state")),
        )
        return

    difficulty_en = map_difficulty_to_en(config["difficulty"])

    debug_partial_loading(
        "CONTINUE BEFORE CHUNK",
        topic=config.get("topic"),
        difficulty=difficulty_en,
        requested_total=config.get("question_count"),
        quiz_questions_before=get_quiz_question_count(st.session_state.get("quiz_data")),
        state_questions_before=get_state_question_count(st.session_state.get("generation_state")),
        current_page=st.session_state.get("current_page"),
        generation_id=current_generation_id,
    )

    st.session_state.partial_generation_in_progress = True
    st.session_state.partial_generation_in_progress_since = time.time()

    try:
        state_for_chunk = copy.deepcopy(st.session_state.get("generation_state"))

        chunk_result = generate_next_quiz_chunk(
            config["topic"],
            difficulty_en,
            state_for_chunk,
        )

        chunk_state = chunk_result.get("state")
        if not isinstance(chunk_state, dict):
            chunk_state = state_for_chunk

        chunk_quiz = chunk_result.get("quiz")

        debug_partial_loading(
            "CONTINUE AFTER CHUNK",
            chunk_ok=chunk_result.get("ok"),
            chunk_completed=chunk_result.get("completed"),
            chunk_error=chunk_result.get("error"),
            chunk_quiz_questions=get_quiz_question_count(chunk_quiz),
            chunk_state_questions=get_state_question_count(chunk_state),
            quiz_questions_before_save=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions_before_save=get_state_question_count(st.session_state.get("generation_state")),
        )

        if current_generation_id != st.session_state.get("partial_generation_last_generation_id"):
            debug_partial_loading(
                "CONTINUE EXIT - GENERATION ID CHANGED AFTER CHUNK",
                expected_generation_id=current_generation_id,
                actual_generation_id=st.session_state.get("partial_generation_last_generation_id"),
            )
            return

        if not chunk_result["ok"]:
            st.session_state.generation_state = chunk_state

            error_message = (
                chunk_result.get("error")
                or "Nie udało się dograć kolejnych pytań."
            )
            st.session_state.partial_generation_error = error_message

            if should_halt_partial_generation(error_message):
                sync_quiz_data_from_state_if_needed(config)
                st.session_state.partial_generation_halted = True
                debug_partial_loading(
                    "CONTINUE ERROR - HALTED",
                    error=error_message,
                    halted=st.session_state.partial_generation_halted,
                    quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                    state_questions=get_state_question_count(st.session_state.get("generation_state")),
                )
                return

            st.session_state.partial_generation_next_attempt_at = (
                time.time() + PARTIAL_GENERATION_RETRY_DELAY_SECONDS
            )
            sync_quiz_data_from_state_if_needed(config)
            debug_partial_loading(
                "CONTINUE ERROR - RETRY SCHEDULED",
                error=error_message,
                retry_at=st.session_state.partial_generation_next_attempt_at,
                quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                state_questions=get_state_question_count(st.session_state.get("generation_state")),
            )
            return

        raw_quiz = chunk_quiz
        if raw_quiz is None:
            raw_quiz = build_quiz_from_state(
                chunk_state,
                fallback_title=str(config.get("topic") or "Quiz"),
            )

        validate_or_raise(raw_quiz)

        updated_quiz = attach_quiz_metadata(raw_quiz, config)
        updated_quiz["questions"] = updated_quiz.get("questions", [])[
            : config["question_count"]
        ]

        if current_generation_id != st.session_state.get("partial_generation_last_generation_id"):
            debug_partial_loading(
                "CONTINUE EXIT - GENERATION ID CHANGED BEFORE SAVE",
                expected_generation_id=current_generation_id,
                actual_generation_id=st.session_state.get("partial_generation_last_generation_id"),
            )
            return

        debug_partial_loading(
            "CONTINUE BEFORE SAVE",
            updated_quiz_questions=get_quiz_question_count(updated_quiz),
            target_question_count=config.get("question_count"),
        )

        # PL: Najpierw zapisujemy quiz do UI, dopiero potem stan generatora.
        # EN: Save quiz for the UI first, then save generator state.
        st.session_state.quiz_data = updated_quiz
        st.session_state.generation_state = chunk_state
        st.session_state.partial_generation_error = None
        st.session_state.partial_generation_next_attempt_at = 0.0

        debug_partial_loading(
            "CONTINUE AFTER SAVE",
            saved_quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            saved_state_questions=get_state_question_count(st.session_state.get("generation_state")),
            completed_flag=chunk_result.get("completed"),
        )

        if chunk_result.get("completed"):
            sync_quiz_data_from_state_if_needed(config)
            st.session_state.partial_generation_halted = True
            debug_partial_loading(
                "CONTINUE COMPLETED",
                halted=st.session_state.partial_generation_halted,
                final_quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
                final_state_questions=get_state_question_count(st.session_state.get("generation_state")),
            )

    finally:
        st.session_state.partial_generation_in_progress = False
        st.session_state.partial_generation_in_progress_since = 0.0
        debug_partial_loading(
            "CONTINUE FINALLY",
            in_progress=st.session_state.partial_generation_in_progress,
            quiz_questions=get_quiz_question_count(st.session_state.get("quiz_data")),
            state_questions=get_state_question_count(st.session_state.get("generation_state")),
            halted=st.session_state.get("partial_generation_halted"),
        )