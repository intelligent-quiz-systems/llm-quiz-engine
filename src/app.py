import json
import streamlit as st
import time

from screens.screens import (
    init_state,
    inject_css,
    render_config_screen,
    render_quiz_screen,
    render_results_screen,
    DEFAULT_JSON,
)

from llm.llm2 import generate_quiz_2

from validations.validate_quiz import validate_quiz

st.set_page_config(page_title="Quiz Generator", page_icon="🧠", layout="centered")

init_state()
inject_css()

if st.session_state.app_step == "config":
    config = render_config_screen()

    if config and config.get("submitted"):
        
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
        st.session_state.quiz_started_at = time.time()
        st.session_state.history_saved = False

        keys_to_remove = [k for k in st.session_state.keys() if k.startswith("widget_q_")]
        for key in keys_to_remove:
            del st.session_state[key]

        st.rerun()

elif st.session_state.app_step == "quiz":
    render_quiz_screen(st.session_state.quiz_data, st.session_state.config)

elif st.session_state.app_step == "results":
    render_results_screen(st.session_state.quiz_data, st.session_state.config)