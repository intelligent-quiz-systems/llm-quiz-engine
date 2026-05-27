import json
import sys
from pathlib import Path
from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]  # src

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz, TopicFromText
from llm.generation_config import (
    TOPIC_EXTRACTION_CHARS, QUIZ_SOURCE_CONTEXT_CHARS,
    INITIAL_BATCH_SIZE, FALLBACK_BATCH_SIZE, MIN_BATCH_SIZE, MAX_ATTEMPTS_PER_BATCH_SIZE,
    SIMILAR_QUESTION_THRESHOLD,
)
from llm.batch_strategy import run_batched_generation
from llm.generation_state import create_state, format_state_summary
from llm.question_quality import run_quality_checks, format_quality_log

# Import Prompt Managera
from prompt_manager.manager import PromptManager


def extract_topic_from_text(source_text: str) -> str | None:
    if not source_text or not source_text.strip():
        return None

    manager = PromptManager()

    built = manager.build_from_template(
        prompt_name="topic_extraction",
        source_text=source_text[:TOPIC_EXTRACTION_CHARS]
    )

    if not built:
        print("[ERR] Failed to load prompt: topic_extraction")
        return None

    try:
        response_json = run_prompt(built["system"], built["user"], TopicFromText)
        response = TopicFromText.model_validate(response_json)
        topic = response.topic.strip()
        return topic if topic else None
    except Exception:
        return None


def _post_process_quiz(quiz_json: dict, diagnostics_out: dict | None = None) -> dict | None:
    """Validate Pydantic model, run quality checks, and log the final quiz."""
    try:
        Quiz.model_validate(quiz_json)
    except ValidationError as e:
        print("Validation error:", e)
        return None
    issues = run_quality_checks(
        quiz_json.get("questions", []),
        similar_threshold=SIMILAR_QUESTION_THRESHOLD,
    )
    if issues:
        print(format_quality_log(issues))
    if diagnostics_out is not None:
        diagnostics_out["quality_issues"] = [dict(i) for i in issues]
    print("\n===== VALIDATED QUIZ JSON =====")
    print(json.dumps(quiz_json, indent=2, ensure_ascii=False))
    return quiz_json


def generate_quiz(
    topic: str,
    difficulty: str,
    num_questions: int,
    source_text: str | None = None,
    previous_questions: list[str] | None = None,
    diagnostics_out: dict | None = None,
) -> dict | None:
    """
    Orchestrate synchronous quiz generation.
    For background generation use BackgroundGenerationWorker from background_worker.

    diagnostics_out: optional dict populated with GenerationState fields after
    the run. Callers that pass None get identical behaviour.
    """
    state = create_state(topic, difficulty, num_questions, INITIAL_BATCH_SIZE)

    try:
        quiz_json = run_batched_generation(
            topic, difficulty, num_questions, source_text,
            initial_batch_size=INITIAL_BATCH_SIZE,
            fallback_batch_size=FALLBACK_BATCH_SIZE,
            min_batch_size=MIN_BATCH_SIZE,
            max_attempts_per_size=MAX_ATTEMPTS_PER_BATCH_SIZE,
            previous_questions=previous_questions,
            state=state,
        )
    except Exception as e:
        print("Generation error:", e)
        if diagnostics_out is not None:
            diagnostics_out.update(dict(state))
            diagnostics_out["generation_error"] = str(e)
        return None

    print(format_state_summary(state))

    if diagnostics_out is not None:
        diagnostics_out.update(dict(state))

    if quiz_json is None:
        return None

    return _post_process_quiz(quiz_json, diagnostics_out=diagnostics_out)


if __name__ == "__main__":
    quiz = generate_quiz(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5
    )