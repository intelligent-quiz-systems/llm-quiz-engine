import json
import streamlit as st
import time

from screens.screens import (
    QUIZ_PAGE_SIZE,
    init_state,
    inject_css,
    render_config_screen,
    render_generating_screen,
    render_generation_failed_message,
    render_quiz_screen,
    render_results_screen,
)

from rag.load_files import get_uploaded_file_id, read_uploaded_source_file

from llm.llm import extract_topic_from_text
from llm.partial_loading import GenerationStatus

st.set_page_config(page_title="Quiz Generator", page_icon="🧠", layout="centered")

init_state()
inject_css()


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
        source_slices = None
        st.session_state.rag_split_summary = None
        effective_topic = (config.get("topic") or "").strip()

        difficulty_pl = str(config["difficulty"])
        difficulty_map = {
            "Łatwy": "easy",
            "Średni": "medium",
            "Trudny": "hard"
        }
        difficulty_en = difficulty_map.get(difficulty_pl, difficulty_pl)

        if source_mode == "Plik":
            source_file = config.get("source_file")
            if source_file is None:
                st.error("Aby wygenerować quiz z pliku, najpierw załaduj plik .txt lub .pdf.")
                st.stop()

            source_text_raw, source_error = read_uploaded_source_file(source_file)
            if source_error:
                st.error(source_error)
                st.stop()

            from rag.source_slices import build_source_slices_from_file
            source_slices, slice_error, rag_split_summary = build_source_slices_from_file(
                source_text_raw, source_file.name, config["question_count"], difficulty_en
            )
            if slice_error:
                st.error(slice_error)
                st.stop()
            if rag_split_summary.get("questions_capped"):
                st.info(rag_split_summary["clamp_warning"])
            st.session_state.rag_split_summary = rag_split_summary

        elif not effective_topic:
            st.error("Aby wygenerować quiz z tematu, wpisz temat quizu.")
            st.stop()

        effective_question_count = (
            st.session_state.rag_split_summary.get("questions_allowed", config["question_count"])
            if st.session_state.rag_split_summary
            else config["question_count"]
        )

        from llm.background_worker import BackgroundGenerationWorker
        worker = BackgroundGenerationWorker(
            topic=effective_topic,
            difficulty=difficulty_en,
            num_questions=effective_question_count,
            source_text=source_text,
            source_slices=source_slices,
        )
        worker.start()

        st.session_state.generation_worker = worker
        st.session_state.requested_question_count = effective_question_count
        st.session_state.generation_final_status = None
        st.session_state.config = config
        st.session_state.app_step = "generating"

        keys_to_remove = [k for k in st.session_state.keys() if k.startswith("widget_q_")]
        for key in keys_to_remove:
            del st.session_state[key]

        st.rerun()

elif st.session_state.app_step == "generating":
    worker = st.session_state.get("generation_worker")
    if worker is None:
        st.session_state.app_step = "config"
        st.rerun()

    snapshot = worker.get_snapshot()
    partial = snapshot.partial_result
    questions = list(partial.get("questions", [])) if partial else []

    ready = len(questions) >= QUIZ_PAGE_SIZE
    done_with_questions = snapshot.is_done and len(questions) > 0

    if ready or done_with_questions:
        cfg = st.session_state.config
        quiz_title = (partial.get("quiz_title") if partial else None) or cfg.get("topic") or "Quiz"
        quiz = {
            "quiz_title": quiz_title,
            "questions": questions,
            "topic": cfg.get("topic"),
            "difficulty": cfg.get("difficulty"),
            "time_limit": cfg.get("time_limit"),
            "question_count": cfg.get("question_count"),
        }
        st.session_state.quiz_data = quiz
        st.session_state.current_page = 0
        st.session_state.answers = {}
        st.session_state.quiz_deadline = None
        st.session_state.timeout_happened = False
        st.session_state.quiz_started_at = time.time()
        st.session_state.history_saved = False
        st.session_state.app_step = "quiz"
        if snapshot.is_done:
            final_s = partial.get("status", GenerationStatus.COMPLETED) if partial else GenerationStatus.FAILED
            st.session_state.generation_final_status = final_s
            st.session_state.generation_worker = None
        st.rerun()

    elif snapshot.is_done:
        err_detail = f": {snapshot.error}" if snapshot.error else ""
        rag_summary = st.session_state.get("rag_split_summary")
        st.session_state.generation_worker = None
        st.session_state.generation_final_status = None
        st.session_state.requested_question_count = 0
        st.session_state.app_step = "config"
        render_generation_failed_message(err_detail, rag_summary)
        st.stop()

    else:
        render_generating_screen(snapshot, st.session_state.requested_question_count)

elif st.session_state.app_step == "quiz":
    worker = st.session_state.get("generation_worker")
    if worker:
        snapshot = worker.get_snapshot()
        partial = snapshot.partial_result
        if partial and partial.get("questions"):
            st.session_state.quiz_data["questions"] = list(partial["questions"])
            if partial.get("quiz_title"):
                st.session_state.quiz_data["quiz_title"] = partial["quiz_title"]
        if snapshot.is_done:
            final_s = partial.get("status", GenerationStatus.COMPLETED) if partial else GenerationStatus.FAILED
            st.session_state.generation_final_status = final_s
            st.session_state.generation_worker = None
    render_quiz_screen(st.session_state.quiz_data, st.session_state.config)

elif st.session_state.app_step == "results":
    render_results_screen(st.session_state.quiz_data, st.session_state.config)