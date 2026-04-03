import json

import streamlit as st

from screens.screens import (
    init_state,
    inject_css,
    render_config_screen,
    render_quiz_screen,
    render_results_screen,
    DEFAULT_JSON,
)

# alternative LLM communication implementations
from llm.llm import generate_quiz
from llm.llm2 import generate_quiz_2

from llm.partial_loading import (
    continue_partial_quiz_flow,
    ensure_partial_generation_defaults,
    get_partial_loading_status,
    reset_partial_generation_session,
    start_partial_quiz_flow,
)

from validations.validate_quiz import validate_quiz

# PL: Przełącznik nowej ścieżki partial loading.
# EN: Toggle for the new partial loading path.
USE_PARTIAL_LOADING = True

st.set_page_config(page_title="Quiz Generator", page_icon="🧠", layout="centered")

init_state()
ensure_partial_generation_defaults()
inject_css()

if st.session_state.app_step == "config":
    config = render_config_screen()

    if config and config.get("submitted"):
        reset_partial_generation_session()

        if USE_PARTIAL_LOADING:
            try:
                start_partial_quiz_flow(config)
                st.rerun()
            except Exception as e:
                st.error(str(e))
                st.stop()

        else:
            difficulty_pl = str(config["difficulty"])

            difficulty_map = {
                "Łatwy": "easy",
                "Średni": "medium",
                "Trudny": "hard"
            }

            difficulty_en = difficulty_map.get(difficulty_pl, difficulty_pl)

            raw_quiz = generate_quiz_2(
                config["topic"],
                difficulty_en,
                config["question_count"]
            )

            is_valid, error_message = validate_quiz(raw_quiz)
            if not is_valid:
                st.error(f"Niepoprawny format quizu: {error_message}")
                st.stop()

            quiz = raw_quiz.copy()
            quiz["topic"] = config.get("topic")
            quiz["difficulty"] = config.get("difficulty")
            quiz["time_limit"] = config.get("time_limit")
            quiz["question_count"] = config.get("question_count")

            st.session_state.quiz_data = quiz
            st.session_state.current_page = 0
            st.session_state.app_step = "quiz"
            st.session_state.config = config
            st.session_state.quiz_deadline = None
            st.session_state.answers = {}
            st.session_state.timeout_happened = False

            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("widget_q_")]
            for key in keys_to_remove:
                del st.session_state[key]

            st.rerun()

elif st.session_state.app_step == "quiz":
    if USE_PARTIAL_LOADING:
        try:
            continue_partial_quiz_flow()
        except Exception as e:
            st.session_state.partial_generation_error = str(e)

        partial_status = get_partial_loading_status()
        if partial_status:
            status_type, status_message = partial_status

            if status_type == "info":
                st.info(status_message)
            elif status_type == "success":
                st.success(status_message)
            elif status_type == "warning":
                st.warning(status_message)

    render_quiz_screen(st.session_state.quiz_data, st.session_state.config)

elif st.session_state.app_step == "results":
    render_results_screen(st.session_state.quiz_data, st.session_state.config)