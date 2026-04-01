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


def compact_error_details(message: str, max_length: int = 260) -> str:
    cleaned = " ".join(str(message).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length] + "..."


def classify_reject_reason(error_message: str) -> str:
    message = error_message.lower()

    if "json_validate_failed" in message:
        return "json_validate_failed"
    if "max_output_tokens" in message and "incomplete" in message:
        return "incomplete_max_output_tokens"
    if "incomplete" in message:
        return "incomplete_response"
    if "rate limit" in message or "error code: 429" in message or "429" in message:
        return "rate_limit"
    return "llm_error"


def get_attempt_label(
    attempted_batch_size: int,
    primary_batch_size: int,
    fallback_batch_size: int,
) -> str:
    if attempted_batch_size == primary_batch_size:
        return "PRIMARY"
    if attempted_batch_size == fallback_batch_size and fallback_batch_size < primary_batch_size:
        return "FALLBACK"
    return "EMERGENCY"


def reject_batch(
    reject_reason: str,
    error_details: str | None = None,
) -> dict:
    return {
        "ok": False,
        "reject_reason": reject_reason,
        "error_details": error_details,
        "quiz": None,
        "output_tokens": None,
        "returned_questions": 0,
    }


def accept_batch(
    quiz_json: dict,
    output_tokens: int | None,
    returned_questions: int,
) -> dict:
    return {
        "ok": True,
        "reject_reason": None,
        "error_details": None,
        "quiz": quiz_json,
        "output_tokens": output_tokens,
        "returned_questions": returned_questions,
    }


def generate_quiz_batch(topic: str, difficulty: str, num_questions: int) -> dict:
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
            return reject_batch(
                reject_reason="wrong_question_count",
                error_details=(
                    f"requested_questions={num_questions}, "
                    f"returned_questions={returned_questions}"
                ),
            )

        return accept_batch(
            quiz_json=quiz_json,
            output_tokens=output_tokens,
            returned_questions=returned_questions,
        )

    except ValidationError as e:
        return reject_batch(
            reject_reason="validation_error",
            error_details=compact_error_details(str(e)),
        )

    except Exception as e:
        message = str(e)
        return reject_batch(
            reject_reason=classify_reject_reason(message),
            error_details=compact_error_details(message),
        )


def generate_quiz_2(topic: str, difficulty: str, num_questions: int) -> dict | None:
    if num_questions < 1 or num_questions > DEFAULT_BATCH_QUESTION_LIMIT:
        print(
            f"Invalid question count: {num_questions}. "
            f"Allowed range is 1-{DEFAULT_BATCH_QUESTION_LIMIT}."
        )
        return None

    accepted_questions = []
    final_quiz_title = topic
    batch_number = 1

    while len(accepted_questions) < num_questions:
        remaining_questions = num_questions - len(accepted_questions)
        accepted_batch = None

        primary_batch_size = normalize_batch_size(INITIAL_BATCH_SIZE, remaining_questions)
        fallback_batch_size = normalize_batch_size(FALLBACK_BATCH_SIZE, remaining_questions)

        attempted_batch_size = primary_batch_size
        attempt_number = 1

        while attempted_batch_size > 0:
            attempt_label = get_attempt_label(
                attempted_batch_size=attempted_batch_size,
                primary_batch_size=primary_batch_size,
                fallback_batch_size=fallback_batch_size,
            )

            print("\n===== BATCH SEARCH =====")
            print(f"batch_number: {batch_number}")
            print(f"attempt_number: {attempt_number}")
            print(f"attempt_label: {attempt_label}")
            print(f"remaining_questions: {remaining_questions}")
            print(f"trying_batch_size: {attempted_batch_size}")

            batch_result = generate_quiz_batch(topic, difficulty, attempted_batch_size)

            if batch_result["ok"]:
                accepted_batch = batch_result
                break

            reject_reason = batch_result["reject_reason"]
            error_details = batch_result["error_details"]

            print("\n===== BATCH REJECTED =====")
            print(f"batch_number: {batch_number}")
            print(f"attempt_number: {attempt_number}")
            print(f"attempt_label: {attempt_label}")
            print(f"requested_in_batch: {attempted_batch_size}")
            print(f"reject_reason: {reject_reason}")
            if error_details:
                print(f"error_details: {error_details}")

            if (
                attempted_batch_size == primary_batch_size
                and fallback_batch_size < primary_batch_size
            ):
                print("\n===== BATCH FALLBACK =====")
                print(f"batch_number: {batch_number}")
                print(f"fallback_reason: {reject_reason}")
                print(f"fallback_from: {attempted_batch_size}")
                print(f"fallback_to: {fallback_batch_size}")

                attempted_batch_size = fallback_batch_size
            else:
                next_batch_size = reduce_batch_size(
                    attempted_batch_size,
                    remaining_questions,
                )

                if next_batch_size > 0:
                    print("\n===== BATCH REDUCE =====")
                    print(f"batch_number: {batch_number}")
                    print(f"reduce_reason: {reject_reason}")
                    print(f"reduce_from: {attempted_batch_size}")
                    print(f"reduce_to: {next_batch_size}")

                attempted_batch_size = next_batch_size

            attempt_number += 1

        if accepted_batch is None:
            print("\n===== BATCH FAILED =====")
            print(f"batch_number: {batch_number}")
            print("LLM error: could not generate a valid batch.")
            return None

        batch_quiz = accepted_batch["quiz"]
        batch_questions = batch_quiz.get("questions", [])
        output_tokens = accepted_batch.get("output_tokens")
        returned_questions = accepted_batch.get("returned_questions", len(batch_questions))

        accepted_questions.extend(batch_questions)

        if batch_quiz.get("quiz_title"):
            final_quiz_title = batch_quiz["quiz_title"]

        remaining_questions = num_questions - len(accepted_questions)

        print("\n===== BATCH ACCEPTED =====")
        print(f"batch_number: {batch_number}")
        print(f"accepted_now: {len(batch_questions)}")
        print(f"accepted_total: {len(accepted_questions)}")
        print(f"remaining_questions: {remaining_questions}")
        print(f"returned_questions: {returned_questions}")
        print(f"output_tokens: {output_tokens}")

        batch_number += 1

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