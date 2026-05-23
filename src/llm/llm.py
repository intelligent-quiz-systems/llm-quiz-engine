import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]  # src

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz, TopicFromText
from llm.generation_config import TOPIC_EXTRACTION_CHARS, QUIZ_SOURCE_CONTEXT_CHARS
from llm.provider_errors import classify_provider_error, format_error_log

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
        print("Błąd: nie udało się pobrać promptu topic_extraction")
        return None

    try:
        response_json = run_prompt(built["system"], built["user"], TopicFromText)
        response = TopicFromText.model_validate(response_json)
        topic = response.topic.strip()
        return topic if topic else None
    except Exception as e:
        info = classify_provider_error(e)
        print(format_error_log(info))
        return None


def generate_quiz(
    topic: str,
    difficulty: str,
    num_questions: int,
    source_text: str | None = None
) -> str | None:
    
    manager = PromptManager()

    built = manager.build_from_template(
        prompt_name="quiz_generation",
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        source_text=source_text[:QUIZ_SOURCE_CONTEXT_CHARS] if source_text else "No source text provided."
    )

    if not built:
        print("Błąd: nie udało się pobrać promptu quiz_generation")
        return None

    try:
        quiz_json = run_prompt(built["system"], built["user"], Quiz)

        print("\n===== RESULT QUIZ JSON =====")
        print(quiz_json)

        quiz = Quiz.model_validate(quiz_json)

        formatted_quiz_json = json.dumps(quiz_json, indent=2, ensure_ascii=False)

        print("\n===== VALIDATED QUIZ JSON =====")
        print(formatted_quiz_json)

        return quiz_json

    except Exception as e:
        info = classify_provider_error(e)
        print(format_error_log(info))
        return None


if __name__ == "__main__":
    quiz = generate_quiz(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5
    )