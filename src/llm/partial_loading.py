import re
import time

import streamlit as st

from llm.llm2 import (
    generate_next_quiz_chunk,
    start_partial_quiz_generation,
)
from validations.validate_quiz import validate_quiz

PARTIAL_GENERATION_RETRY_DELAY_SECONDS = 1.5
LONG_PROVIDER_WAIT_THRESHOLD_SECONDS = 60.0


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
    st.session_state.partial_generation_halted = bool(partial_result.get("completed"))
    st.session_state.partial_generation_next_attempt_at = 0.0
    st.session_state.partial_generation_last_generation_id = generation_id

    clear_question_widget_keys()


def continue_partial_quiz_flow() -> None:
    config = st.session_state.get("config")
    quiz = st.session_state.get("quiz_data")
    state = st.session_state.get("generation_state")

    if not config or not quiz or not state:
        return

    if state.get("completed"):
        st.session_state.partial_generation_halted = True
        return

    if state.get("failed"):
        st.session_state.partial_generation_error = state.get("last_error")
        st.session_state.partial_generation_halted = True
        return

    if st.session_state.get("partial_generation_halted", False):
        return

    if st.session_state.get("partial_generation_in_progress", False):
        return

    next_attempt_at = st.session_state.get("partial_generation_next_attempt_at", 0.0)
    if time.time() < next_attempt_at:
        return

    current_generation_id = st.session_state.get("partial_generation_last_generation_id")
    if not current_generation_id:
        return

    difficulty_en = map_difficulty_to_en(config["difficulty"])

    st.session_state.partial_generation_in_progress = True

    try:
        chunk_result = generate_next_quiz_chunk(
            config["topic"],
            difficulty_en,
            state,
        )

        if current_generation_id != st.session_state.get("partial_generation_last_generation_id"):
            return

        st.session_state.generation_state = chunk_result.get("state", state)

        if not chunk_result["ok"]:
            error_message = (
                chunk_result.get("error")
                or "Nie udało się dograć kolejnych pytań."
            )
            st.session_state.partial_generation_error = error_message

            if should_halt_partial_generation(error_message):
                st.session_state.partial_generation_halted = True
                return

            st.session_state.partial_generation_next_attempt_at = (
                time.time() + PARTIAL_GENERATION_RETRY_DELAY_SECONDS
            )
            return

        raw_quiz = chunk_result.get("quiz")
        validate_or_raise(raw_quiz)

        updated_quiz = attach_quiz_metadata(raw_quiz, config)

        if current_generation_id != st.session_state.get("partial_generation_last_generation_id"):
            return

        updated_quiz["questions"] = updated_quiz.get("questions", [])[
            : config["question_count"]
        ]

        st.session_state.quiz_data = updated_quiz
        st.session_state.partial_generation_error = None
        st.session_state.partial_generation_next_attempt_at = 0.0

        if chunk_result.get("completed"):
            st.session_state.partial_generation_halted = True

    finally:
        st.session_state.partial_generation_in_progress = False