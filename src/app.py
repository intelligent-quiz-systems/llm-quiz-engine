import json
import streamlit as st
import time
import hashlib
from io import BytesIO
from pypdf import PdfReader

from screens.screens import (
    init_state,
    inject_css,
    render_config_screen,
    render_quiz_screen,
    render_results_screen,
    DEFAULT_JSON,
    MAX_SOURCE_FILE_SIZE_BYTES,
    format_size_label,
)

from llm.llm import generate_quiz, extract_topic_from_text

from validations.validate_quiz import validate_quiz

st.set_page_config(page_title="Quiz Generator", page_icon="🧠", layout="centered")

init_state()
inject_css()


def read_uploaded_source_file(uploaded_file):
    if uploaded_file is None:
        return None, None

    if uploaded_file.size > MAX_SOURCE_FILE_SIZE_BYTES:
        return (
            None,
            f"Plik jest za duży. Maksymalny rozmiar to {format_size_label(MAX_SOURCE_FILE_SIZE_BYTES)}.",
        )

    file_name = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()

    if file_name.endswith(".txt"):
        try:
            source_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            source_text = file_bytes.decode("utf-8", errors="ignore")
    elif file_name.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(file_bytes))
            source_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception:
            return None, "Nie udało się odczytać pliku PDF."
    else:
        return None, "Dozwolone są tylko pliki .txt oraz .pdf."

    if not source_text or not source_text.strip():
        return None, "Plik nie zawiera możliwego do odczytu tekstu."

    return source_text.strip(), None


def get_uploaded_file_id(uploaded_file):
    if uploaded_file is None:
        return None
    payload = uploaded_file.getvalue()
    return hashlib.sha256(payload).hexdigest()


if st.session_state.app_step == "config":
    config = render_config_screen()

    if config:
        source_file = config.get("source_file")
        source_file_id = get_uploaded_file_id(source_file)

        if source_file is None:
            st.session_state.source_topic_file_id = None

        elif source_file_id != st.session_state.get("source_topic_file_id"):
            source_text_for_topic, source_error_for_topic = read_uploaded_source_file(source_file)
            if source_error_for_topic:
                st.error(source_error_for_topic)
                st.stop()

            extracted_topic = extract_topic_from_text(source_text_for_topic)
            if extracted_topic:
                st.session_state.pending_topic_input = extracted_topic

            st.session_state.source_topic_file_id = source_file_id
            st.rerun()

        elif st.session_state.get("source_topic_file_id"):
            st.info("Temat quizu został ustawiony automatycznie na podstawie załadowanego pliku.")

    if config and config.get("submitted"):
        source_mode = config.get("source_mode")
        source_text = None
        effective_topic = (config.get("topic") or "").strip()

        if source_mode == "Plik":
            if config.get("source_file") is None:
                st.error("Aby wygenerować quiz z pliku, najpierw załaduj plik .txt lub .pdf.")
                st.stop()

            source_text, source_error = read_uploaded_source_file(config.get("source_file"))
            if source_error:
                st.error(source_error)
                st.stop()
        elif not effective_topic:
            st.error("Aby wygenerować quiz z tematu, wpisz temat quizu.")
            st.stop()

        difficulty_pl = str(config["difficulty"])

        difficulty_map = {
            "Łatwy": "easy",
            "Średni": "medium",
            "Trudny": "hard"
        }

        difficulty_en = difficulty_map.get(difficulty_pl, difficulty_pl)      

        raw_quiz = generate_quiz(
            effective_topic,
            difficulty_en,
            config["question_count"],
            source_text=source_text,
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