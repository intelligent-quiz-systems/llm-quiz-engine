import json
import sys
from pathlib import Path

from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz

HARD_MAX_OUTPUT_TOKENS = 2200
DEFAULT_BATCH_QUESTION_LIMIT = 100
INITIAL_BATCH_SIZE = 10
FALLBACK_BATCH_SIZE = 5

# Przełączniki debugowe dla szczegółowych sekcji logów.
# Tymczasowo wyłączone, ponieważ zaśmiecały terminal podczas bieżących testów.
# Zostawione w kodzie, aby można je było łatwo ponownie włączyć w razie potrzeby.
# Debug log toggles for verbose output sections.
# Temporarily disabled because they cluttered terminal output during normal testing.
# Kept in code for quick re-enabling if deeper diagnostics are needed later.
SHOW_RESULT_QUIZ_JSON = False
SHOW_VALIDATED_QUIZ_JSON = False


def normalize_batch_size(batch_size: int, remaining_questions: int) -> int:
    if remaining_questions <= 0:
        return 0
    if batch_size < 1:
        batch_size = 1
    return min(batch_size, remaining_questions)


def reduce_batch_size(current_batch_size: int, remaining_questions: int) -> int:
    if current_batch_size <= 1:
        return 0

    reduced = current_batch_size - 1
    return normalize_batch_size(reduced, remaining_questions)


def generate_quiz_batch(topic: str, difficulty: str, num_questions: int) -> dict | None:
    system_prompt = """
        You are a quiz generator.

        You must return ONLY valid JSON.
        Do not include explanations, comments, markdown or text outside JSON.

        The JSON must strictly follow this structure:

        {
          "quiz_title": "string",
          "questions": [
            {
              "question": "string",
              "options": ["string", "string", "string", "string"],
              "correct_index": 0
            }
          ]
        }

        Rules:
        - quiz_title must be a non-empty string
        - options must contain exactly 4 answers
        - correct_index must be an integer from 0 to 3
        - return exactly the requested number of questions
    """

    user_prompt = f"""
        Generate a quiz in Polish.

        Topic: {topic}
        Difficulty: {difficulty}

        Requirements:
        - exactly {num_questions} questions
        - each question must have exactly 4 options
        - correct_index must be between 0 and 3
        - include quiz_title

        Return ONLY JSON.
    """

    try:
        prompt_result = run_prompt(
            system_prompt,
            user_prompt,
            Quiz,
            requested_questions=num_questions,
            max_output_tokens=HARD_MAX_OUTPUT_TOKENS,
        )

        quiz_json = prompt_result["quiz"]
        output_tokens = prompt_result.get("output_tokens")

        if SHOW_RESULT_QUIZ_JSON:
            print("\n===== RESULT QUIZ JSON =====")
            print(quiz_json)

        Quiz.model_validate(quiz_json)

        formatted_quiz_json = json.dumps(quiz_json, indent=2, ensure_ascii=False)

        if SHOW_VALIDATED_QUIZ_JSON:
            print("\n===== VALIDATED QUIZ JSON =====")
            print(formatted_quiz_json)

        returned_questions = len(quiz_json.get("questions", []))
        if returned_questions != num_questions:
            print(
                f"Batch rejected: requested_questions={num_questions}, "
                f"returned_questions={returned_questions}"
            )
            return None

        return {
            "quiz": quiz_json,
            "output_tokens": output_tokens,
            "returned_questions": returned_questions,
        }

    except ValidationError as e:
        print("Validation error:", e)
        return None

    except Exception as e:
        print("LLM error:", e)
        return None


def generate_quiz_2(topic: str, difficulty: str, num_questions: int) -> dict | None:
    if num_questions < 1 or num_questions > DEFAULT_BATCH_QUESTION_LIMIT:
        print(
            f"Invalid question count: {num_questions}. "
            f"Allowed range is 1-{DEFAULT_BATCH_QUESTION_LIMIT}."
        )
        return None

    accepted_questions = []
    final_quiz_title = topic

    while len(accepted_questions) < num_questions:
        remaining_questions = num_questions - len(accepted_questions)
        accepted_batch = None

        primary_batch_size = normalize_batch_size(INITIAL_BATCH_SIZE, remaining_questions)
        fallback_batch_size = normalize_batch_size(FALLBACK_BATCH_SIZE, remaining_questions)

        attempted_batch_size = primary_batch_size

        while attempted_batch_size > 0:
            print("\n===== BATCH SEARCH =====")
            print(f"remaining_questions: {remaining_questions}")
            print(f"trying_batch_size: {attempted_batch_size}")

            batch_result = generate_quiz_batch(topic, difficulty, attempted_batch_size)

            if batch_result is not None:
                accepted_batch = batch_result
                break

            if (
                attempted_batch_size == primary_batch_size
                and fallback_batch_size < primary_batch_size
            ):
                attempted_batch_size = fallback_batch_size
            else:
                attempted_batch_size = reduce_batch_size(
                    attempted_batch_size,
                    remaining_questions,
                )

        if accepted_batch is None:
            print("LLM error: could not generate a valid batch.")
            return None

        batch_quiz = accepted_batch["quiz"]
        batch_questions = batch_quiz.get("questions", [])
        output_tokens = accepted_batch.get("output_tokens")

        accepted_questions.extend(batch_questions)

        if batch_quiz.get("quiz_title"):
            final_quiz_title = batch_quiz["quiz_title"]

        remaining_questions = num_questions - len(accepted_questions)

        print("\n===== BATCH ACCEPTED =====")
        print(f"accepted_now: {len(batch_questions)}")
        print(f"accepted_total: {len(accepted_questions)}")
        print(f"remaining_questions: {remaining_questions}")
        print(f"output_tokens: {output_tokens}")

    final_quiz = {
        "quiz_title": final_quiz_title,
        "questions": accepted_questions[:num_questions],
    }

    try:
        Quiz.model_validate(final_quiz)
        return final_quiz

    except ValidationError as e:
        print("Final quiz validation error:", e)
        return None


if __name__ == "__main__":
    quiz = generate_quiz_2(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5,
    )