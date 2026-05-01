import json
import sys
from pathlib import Path
from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]  # src

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz, TopicFromText

TOPIC_EXTRACTION_CHARS = 1000
QUIZ_SOURCE_CONTEXT_CHARS = 10000


def extract_topic_from_text(source_text: str) -> str | None:
    if not source_text or not source_text.strip():
        return None

    system_prompt = (
    """
        You are a topic extraction assistant.
        Return ONLY valid JSON with one field:
        {
          "topic": "string"
        }
        Rules:
        - topic must be short and specific
        - topic must be in Polish
        - max 8 words
    """
    )

    user_prompt = (
       f"""
        Extract the main topic from this text:

        {source_text[:TOPIC_EXTRACTION_CHARS]}

        Return ONLY JSON.
        """
    )

    try:
        response_json = run_prompt(system_prompt, user_prompt, TopicFromText)
        response = TopicFromText.model_validate(response_json)
        topic = response.topic.strip()
        return topic if topic else None
    except Exception:
        return None


def generate_quiz(
    topic: str,
    difficulty: str,
    num_questions: int,
    source_text: str | None = None
) -> str | None:
    system_prompt = (
    """
        You are a quiz generator.

        You must return ONLY valid JSON.
        Do not include explanations, comments, markdown or text outside JSON.

        The JSON must strictly follow this structure:

        {
        "questions": [
            {
            "question": "string",
            "options": ["string", "string", "string", "string"],
            "correct_index": 0
            }
        ]
        }

        Rules:
        - options must contain exactly 4 answers
        - correct_index must be an integer from 0 to 3
        - return exactly the requested number of questions
    """
    )

    user_prompt = (
       f"""
        Generate a quiz in Polish.

        Topic: {topic}
        Difficulty: {difficulty}
        Source context text:
        {source_text[:QUIZ_SOURCE_CONTEXT_CHARS] if source_text else "No source text provided."}

        Requirements:
        - exactly {num_questions} questions
        - each question must have exactly 4 options
        - correct_index must be between 0 and 3
        - if source context text is provided: base ALL questions strictly on source context text
        - if source context text is not provided: base questions on topic only

        Return ONLY JSON.
        """
    )

    try:
        quiz_json = run_prompt(system_prompt, user_prompt, Quiz)

        print("\n===== RESULT QUIZ JSON =====")
        print(quiz_json )

        # Validate returned JSON against the Pydantic model
        quiz = Quiz.model_validate(quiz_json)

        formatted_quiz_json = json.dumps(quiz_json, indent=2, ensure_ascii=False)

        print("\n===== VALIDATED QUIZ JSON =====")
        print(formatted_quiz_json)

        return quiz_json

    except ValidationError as e:
        print("Validation error:", e)
        return None

    except Exception as e:
        print("LLM error:", e)
        return None


if __name__ == "__main__":
    quiz = generate_quiz(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5
    )
