import streamlit as st
import time

from screens.screens import (
    init_state,
    inject_css,
    render_config_screen,
    render_quiz_screen,
    render_results_screen,
)

from rag.load_files import get_uploaded_file_id, read_uploaded_source_file
from rag.rag import build_rag_pipeline, make_file_source, serialize_rag_logs

from llm.llm import generate_quiz, extract_topic_from_text
from validations.validate_quiz import validate_quiz

st.set_page_config(page_title="Quiz Generator", page_icon="🧠", layout="centered")

init_state()
inject_css()


def map_difficulty_to_english(difficulty_pl: str) -> str:
    difficulty_map = {
        "Łatwy": "easy",
        "Średni": "medium",
        "Trudny": "hard",
    }
    return difficulty_map.get(difficulty_pl, difficulty_pl)


def build_rag_context_from_uploaded_file(uploaded_file):
    source_text, source_error = read_uploaded_source_file(uploaded_file)
    if source_error:
        return None, None, source_error

    source = make_file_source(
        source_id="src_1",
        file_name=uploaded_file.name,
        extracted_text=source_text,
    )

    try:
        chunks, batches, logs = build_rag_pipeline([source])
    except ValueError as exc:
        return None, None, str(exc)

    if not batches:
        return None, None, "Nie udało się utworzyć żadnych batchy RAG z załadowanego pliku."

    rag_context = "\n\n".join(batch.context_text for batch in batches)
    rag_metadata = {
        "source_name": uploaded_file.name,
        "chunk_count": len(chunks),
        "batch_count": len(batches),
        "logs": serialize_rag_logs(logs),
    }

    return rag_context, rag_metadata, None


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
        rag_metadata = None
        effective_topic = (config.get("topic") or "").strip()

        if source_mode == "Plik":
            source_file = config.get("source_file")
            if source_file is None:
                st.error("Aby wygenerować quiz z pliku, najpierw załaduj plik .txt lub .pdf.")
                st.stop()

            source_text, rag_metadata, source_error = build_rag_context_from_uploaded_file(source_file)
            if source_error:
                st.error(source_error)
                st.stop()

        elif not effective_topic:
            st.error("Aby wygenerować quiz z tematu, wpisz temat quizu.")
            st.stop()

        difficulty_pl = str(config["difficulty"])
        difficulty_en = map_difficulty_to_english(difficulty_pl)

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

        if rag_metadata:
            quiz["rag_enabled"] = True
            quiz["rag_source_name"] = rag_metadata["source_name"]
            quiz["rag_chunk_count"] = rag_metadata["chunk_count"]
            quiz["rag_batch_count"] = rag_metadata["batch_count"]
            quiz["rag_logs"] = rag_metadata["logs"]
        else:
            quiz["rag_enabled"] = False
            quiz["rag_logs"] = []

        st.session_state.quiz_data = quiz
        st.session_state.current_page = 0
        st.session_state.app_step = "quiz"
        st.session_state.config = config
        st.session_state.quiz_deadline = None
        st.session_state.answers = {}
        st.session_state.timeout_happened = False
        st.session_state.quiz_started_at = time.time()
        st.session_state.history_saved = False

        keys_to_remove = [key for key in st.session_state.keys() if key.startswith("widget_q_")]
        for key in keys_to_remove:
            del st.session_state[key]

        st.rerun()

elif st.session_state.app_step == "quiz":
    render_quiz_screen(st.session_state.quiz_data, st.session_state.config)

elif st.session_state.app_step == "results":
    render_results_screen(st.session_state.quiz_data, st.session_state.config)