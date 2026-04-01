import json
import time
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

        # Start pomiaru:
        # liczymy od momentu wysłania danych użytkownika do modelu,
        # czyli tuż przed uruchomieniem generate_quiz_2(...).
        st.session_state.generation_started_at = time.perf_counter()
        st.session_state.generation_input_topic = config["topic"]
        st.session_state.generation_input_difficulty = difficulty_pl
        st.session_state.generation_input_question_count = config["question_count"]
        st.session_state.generation_summary_logged = False
        st.session_state.generation_time_seconds = None
        st.session_state.average_time_per_question_seconds = None

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
    # Koniec pomiaru:
    # logujemy czas przy pierwszym wejściu na ekran quizu,
    # czyli praktycznie w momencie, gdy pytania mają się wyświetlić użytkownikowi.
    if not st.session_state.get("generation_summary_logged", False):
        started_at = st.session_state.get("generation_started_at")

        if started_at is not None:
            generation_time_seconds = time.perf_counter() - started_at

            quiz_data = st.session_state.get("quiz_data")
            generated_questions = 0
            if isinstance(quiz_data, dict):
                generated_questions = len(quiz_data.get("questions", []))

            average_time_per_question = (
                generation_time_seconds / generated_questions
                if generated_questions > 0
                else 0.0
            )

            st.session_state.generation_time_seconds = generation_time_seconds
            st.session_state.average_time_per_question_seconds = average_time_per_question
            st.session_state.generation_summary_logged = True

            print("\n===== QUIZ GENERATION SUMMARY =====")
            print(f"topic: {st.session_state.get('generation_input_topic', 'N/A')}")
            print(f"difficulty: {st.session_state.get('generation_input_difficulty', 'N/A')}")
            print(f"requested_questions: {st.session_state.get('generation_input_question_count', 'N/A')}")
            print(f"generated_questions: {generated_questions}")
            print(f"generation_time_seconds: {generation_time_seconds:.2f}")
            print(f"average_time_per_question_seconds: {average_time_per_question:.2f}")

    render_quiz_screen(st.session_state.quiz_data, st.session_state.config)

elif st.session_state.app_step == "results":
    render_results_screen(st.session_state.quiz_data, st.session_state.config)