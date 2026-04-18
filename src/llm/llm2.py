import json
import re
import sys
import time
from pathlib import Path

from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz
from llm.quiz_debug_checks import (
    check_question_structure,
    find_duplicate_questions,
    find_similar_questions,
)

HARD_MAX_OUTPUT_TOKENS = 2200
DEFAULT_BATCH_QUESTION_LIMIT = 100
INITIAL_BATCH_SIZE = 10
FALLBACK_BATCH_SIZE = 5
MIN_SAFE_BATCH_SIZE = 3
MAX_RETRIES_PER_BATCH_SIZE = 2
MAX_RATE_LIMIT_RETRIES_PER_BATCH_SIZE = 2
SIMILAR_QUESTION_THRESHOLD = 0.88
OUTPUT_BATCH_STEP_DOWN = 2
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 3.0
MIN_RATE_LIMIT_WAIT_SECONDS = 0.5
MAX_RATE_LIMIT_WAIT_SECONDS = 8.0
LONG_RATE_LIMIT_WAIT_THRESHOLD_SECONDS = 60.0
RECENT_QUESTION_AVOID_LIMIT = 12

# PL: Przełączniki debugowe dla szczegółowych sekcji logów.
# EN: Debug toggles for verbose log sections.
SHOW_RESULT_QUIZ_JSON = False
SHOW_VALIDATED_QUIZ_JSON = False
SHOW_OUTPUT_FAILURE_DEBUG = True

QUALITY_REJECT_REASONS = {
    "structure_issues",
    "duplicate_questions",
    "similar_questions",
}

OUTPUT_REJECT_REASONS = {
    "json_validate_failed",
    "incomplete_max_output_tokens",
    "incomplete_response",
    "wrong_question_count",
}


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


def compact_issue_list(
    issues: list[str],
    max_items: int = 3,
    max_length: int = 260,
) -> str:
    preview = issues[:max_items]
    summary = " | ".join(preview)

    if len(issues) > max_items:
        summary += f" | ... (+{len(issues) - max_items} more)"

    return compact_error_details(summary, max_length=max_length)


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


def classify_reject_family(reject_reason: str) -> str:
    if reject_reason in QUALITY_REJECT_REASONS:
        return "quality"
    if reject_reason in OUTPUT_REJECT_REASONS:
        return "output"
    if reject_reason == "rate_limit":
        return "rate_limit"
    return "other"


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


def evaluate_batch_quality(quiz_json: dict) -> dict | None:
    structure_issues = check_question_structure(quiz_json)
    if structure_issues:
        return reject_batch(
            reject_reason="structure_issues",
            error_details=compact_issue_list(structure_issues),
        )

    duplicate_questions = find_duplicate_questions(quiz_json)
    if duplicate_questions:
        return reject_batch(
            reject_reason="duplicate_questions",
            error_details=compact_issue_list(duplicate_questions),
        )

    similar_questions = find_similar_questions(
        quiz_json,
        threshold=SIMILAR_QUESTION_THRESHOLD,
    )
    if similar_questions:
        return reject_batch(
            reject_reason="similar_questions",
            error_details=compact_issue_list(similar_questions),
        )

    return None


def normalize_question_text(text: str) -> str:
    normalized = str(text).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[?!.]+$", "", normalized)
    return normalized


def extract_recent_question_texts(
    state: dict,
    limit: int = RECENT_QUESTION_AVOID_LIMIT,
) -> list[str]:
    accepted_questions = state.get("accepted_questions", [])
    recent_questions = accepted_questions[-limit:]

    seen: set[str] = set()
    result: list[str] = []

    for question in recent_questions:
        question_text = question.get("question")
        if not isinstance(question_text, str):
            continue

        cleaned_question_text = question_text.strip()
        if not cleaned_question_text:
            continue

        normalized_question_text = normalize_question_text(cleaned_question_text)
        if normalized_question_text in seen:
            continue

        seen.add(normalized_question_text)
        result.append(cleaned_question_text)

    return result


def build_recent_question_guardrail(question_texts: list[str]) -> str:
    if not question_texts:
        return ""

    formatted_questions = "\n".join(
        f"- {question_text}"
        for question_text in question_texts
    )

    return f"""
Already accepted recent question stems. Do not repeat them and do not create near-clones of them:
{formatted_questions}
"""


def find_cross_batch_duplicate_questions(
    state: dict,
    batch_quiz: dict,
) -> list[str]:
    accepted_questions = state.get("accepted_questions", [])
    batch_questions = batch_quiz.get("questions", [])

    accepted_question_positions: dict[str, int] = {}

    for accepted_index, accepted_question in enumerate(accepted_questions, start=1):
        question_text = accepted_question.get("question")
        if not isinstance(question_text, str):
            continue

        normalized_question_text = normalize_question_text(question_text)
        if not normalized_question_text:
            continue

        if normalized_question_text not in accepted_question_positions:
            accepted_question_positions[normalized_question_text] = accepted_index

    issues: list[str] = []
    accepted_count = len(accepted_questions)

    for batch_index, batch_question in enumerate(batch_questions, start=1):
        question_text = batch_question.get("question")
        if not isinstance(question_text, str):
            continue

        normalized_question_text = normalize_question_text(question_text)
        if not normalized_question_text:
            continue

        accepted_index = accepted_question_positions.get(normalized_question_text)
        if accepted_index is None:
            continue

        global_batch_index = accepted_count + batch_index
        issues.append(
            f"Duplicate question: Q{accepted_index} and Q{global_batch_index}"
        )

    return issues


def evaluate_cross_batch_quality(
    state: dict,
    batch_quiz: dict,
) -> dict | None:
    # PL: Zostawiamy exact duplicate między batchami.
    # PL: Cross-batch similar check wyłączamy, bo za bardzo spowalnia generowanie.
    # EN: We keep exact duplicate checks across batches.
    # EN: Cross-batch similar checks are disabled because they slow generation too much.
    accepted_questions = state.get("accepted_questions", [])
    if not accepted_questions:
        return None

    duplicate_questions = find_cross_batch_duplicate_questions(
        state=state,
        batch_quiz=batch_quiz,
    )
    if duplicate_questions:
        return reject_batch(
            reject_reason="duplicate_questions",
            error_details=compact_issue_list(duplicate_questions),
        )

    return None


def lock_safe_batch_size(
    current_locked_batch_size: int,
    new_locked_batch_size: int,
    batch_number: int,
) -> int:
    if new_locked_batch_size < current_locked_batch_size:
        print("\n===== SAFE BATCH MODE LOCKED =====")
        print(f"batch_number: {batch_number}")
        print(f"locked_batch_size: {new_locked_batch_size}")
        print("note: all next batches in this generation will stay at this size or less")
        return new_locked_batch_size

    return current_locked_batch_size


def extract_rate_limit_wait_seconds(error_details: str | None) -> float:
    # PL: Provider może zwrócić wskazówkę w sekundach albo w formacie XmYs.
    # PL: Ta funkcja wyciąga pełny czas oczekiwania, ale do krótkiego sleepa go ograniczamy.
    # EN: The provider may return either seconds or an XmYs wait hint.
    # EN: This function extracts the full wait time, but we clamp it for short sleeps.
    if not error_details:
        return DEFAULT_RATE_LIMIT_WAIT_SECONDS

    minutes_seconds_match = re.search(
        r"try again in\s*([0-9]+)m([0-9]+(?:\.[0-9]+)?)s",
        error_details,
        flags=re.IGNORECASE,
    )
    if minutes_seconds_match:
        try:
            minutes = float(minutes_seconds_match.group(1))
            seconds = float(minutes_seconds_match.group(2))
            wait_seconds = (minutes * 60.0) + seconds
            wait_seconds = max(wait_seconds, MIN_RATE_LIMIT_WAIT_SECONDS)
            wait_seconds = min(wait_seconds, MAX_RATE_LIMIT_WAIT_SECONDS)
            return wait_seconds
        except ValueError:
            return DEFAULT_RATE_LIMIT_WAIT_SECONDS

    seconds_match = re.search(
        r"try again in\s*([0-9]+(?:\.[0-9]+)?)s",
        error_details,
        flags=re.IGNORECASE,
    )
    if not seconds_match:
        return DEFAULT_RATE_LIMIT_WAIT_SECONDS

    try:
        wait_seconds = float(seconds_match.group(1))
    except ValueError:
        return DEFAULT_RATE_LIMIT_WAIT_SECONDS

    wait_seconds = max(wait_seconds, MIN_RATE_LIMIT_WAIT_SECONDS)
    wait_seconds = min(wait_seconds, MAX_RATE_LIMIT_WAIT_SECONDS)
    return wait_seconds


def is_long_rate_limit_wait(error_details: str | None) -> bool:
    # PL: Jeśli provider mówi o TPD albo każe czekać bardzo długo,
    # PL: nie warto retryować w tej samej sesji w kółko.
    # EN: If the provider reports TPD or a very long wait,
    # EN: retrying in a loop in the same session is not worth it.
    if not error_details:
        return False

    lowered = error_details.lower()

    if "tokens per day" in lowered:
        return True

    if "tpd" in lowered:
        return True

    minutes_seconds_match = re.search(
        r"try again in\s*([0-9]+)m([0-9]+(?:\.[0-9]+)?)s",
        error_details,
        flags=re.IGNORECASE,
    )
    if minutes_seconds_match:
        try:
            minutes = float(minutes_seconds_match.group(1))
            seconds = float(minutes_seconds_match.group(2))
            wait_seconds = (minutes * 60.0) + seconds
            return wait_seconds >= LONG_RATE_LIMIT_WAIT_THRESHOLD_SECONDS
        except ValueError:
            return False

    seconds_match = re.search(
        r"try again in\s*([0-9]+(?:\.[0-9]+)?)s",
        error_details,
        flags=re.IGNORECASE,
    )
    if seconds_match:
        try:
            wait_seconds = float(seconds_match.group(1))
            return wait_seconds >= LONG_RATE_LIMIT_WAIT_THRESHOLD_SECONDS
        except ValueError:
            return False

    return False


def build_empty_stats() -> dict:
    # PL: Statystyki całej generacji.
    # EN: Generation-wide statistics.
    return {
        "total_batches": 0,
        "rejected_batches": 0,
        "retry_count": 0,
        "rate_limit_retry_count": 0,
        "rate_limit_reject_count": 0,
        "fallback_10_to_5_count": 0,
        "fallback_5_to_3_count": 0,
        "quality_reject_count": 0,
        "output_reject_count": 0,
        "other_reject_count": 0,
    }


def create_generation_state(num_questions: int) -> dict:
    # PL: Stan partial loading trzymany np. w session_state.
    # EN: Partial loading state that can be stored in session_state.
    return {
        "requested_questions": num_questions,
        "accepted_questions": [],
        "final_quiz_title": None,
        "batch_number": 1,
        "locked_batch_size": INITIAL_BATCH_SIZE,
        "stats": build_empty_stats(),
        "completed": False,
        "failed": False,
        "last_error": None,
    }


def build_quiz_from_state(state: dict, fallback_title: str) -> dict:
    requested_questions = state.get("requested_questions")
    accepted_questions = state.get("accepted_questions", [])

    if isinstance(requested_questions, int) and requested_questions >= 0:
        accepted_questions = accepted_questions[:requested_questions]

    quiz_title = state.get("final_quiz_title") or fallback_title

    return {
        "quiz_title": quiz_title,
        "questions": accepted_questions,
    }


def print_generation_batching_summary(
    topic: str,
    difficulty: str,
    requested_questions: int,
    generated_questions: int,
    locked_batch_size: int,
    stats: dict,
    completed: bool,
) -> None:
    print("\n===== BATCHING GENERATION SUMMARY =====")
    print(f"topic: {topic}")
    print(f"difficulty: {difficulty}")
    print(f"requested_questions: {requested_questions}")
    print(f"generated_questions: {generated_questions}")
    print(f"completed: {completed}")
    print(f"final_locked_batch_size: {locked_batch_size}")
    print(f"total_batches: {stats['total_batches']}")
    print(f"rejected_batches: {stats['rejected_batches']}")
    print(f"retry_count: {stats['retry_count']}")
    print(f"rate_limit_retry_count: {stats['rate_limit_retry_count']}")
    print(f"rate_limit_reject_count: {stats['rate_limit_reject_count']}")
    print(f"fallback_10_to_5_count: {stats['fallback_10_to_5_count']}")
    print(f"fallback_5_to_3_count: {stats['fallback_5_to_3_count']}")
    print(f"quality_reject_count: {stats['quality_reject_count']}")
    print(f"output_reject_count: {stats['output_reject_count']}")
    print(f"other_reject_count: {stats['other_reject_count']}")


def print_output_failure_debug(
    topic: str,
    difficulty: str,
    batch_number: int,
    attempt_label: str,
    attempted_batch_size: int,
    locked_batch_size: int,
    reject_reason: str,
    error_details: str | None,
) -> None:
    if not SHOW_OUTPUT_FAILURE_DEBUG:
        return

    print("\n===== OUTPUT FAILURE DEBUG =====")
    print(f"topic: {topic}")
    print(f"difficulty: {difficulty}")
    print(f"batch_number: {batch_number}")
    print(f"attempt_label: {attempt_label}")
    print(f"requested_in_batch: {attempted_batch_size}")
    print(f"locked_batch_size: {locked_batch_size}")
    print(f"reject_reason: {reject_reason}")

    if error_details:
        print(f"error_details: {error_details}")


def generate_quiz_batch(
    topic: str,
    difficulty: str,
    num_questions: int,
    recent_question_texts: list[str] | None = None,
) -> dict:
    recent_question_texts = recent_question_texts or []
    recent_question_guardrail = build_recent_question_guardrail(recent_question_texts)

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
        - avoid duplicates
        - avoid repeating the same question wording

        {recent_question_guardrail}

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

        quality_result = evaluate_batch_quality(quiz_json)
        if quality_result is not None:
            return quality_result

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


def finalize_generation_success(
    topic: str,
    difficulty: str,
    state: dict,
) -> dict:
    # PL: Składamy finalny quiz i pilnujemy końcowej walidacji.
    # EN: Build the final quiz and enforce final validation.
    final_quiz = build_quiz_from_state(state, fallback_title=topic)

    try:
        Quiz.model_validate(final_quiz)

        state["completed"] = True
        state["failed"] = False
        state["last_error"] = None

        print_generation_batching_summary(
            topic=topic,
            difficulty=difficulty,
            requested_questions=state["requested_questions"],
            generated_questions=len(final_quiz["questions"]),
            locked_batch_size=state["locked_batch_size"],
            stats=state["stats"],
            completed=True,
        )

        return {
            "ok": True,
            "completed": True,
            "failed": False,
            "state": state,
            "quiz": final_quiz,
            "new_questions": [],
            "remaining_questions": 0,
        }

    except ValidationError as e:
        state["completed"] = False
        state["failed"] = True
        state["last_error"] = compact_error_details(str(e))

        print("Final quiz validation error:", e)

        print_generation_batching_summary(
            topic=topic,
            difficulty=difficulty,
            requested_questions=state["requested_questions"],
            generated_questions=len(state["accepted_questions"]),
            locked_batch_size=state["locked_batch_size"],
            stats=state["stats"],
            completed=False,
        )

        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": state,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": state["requested_questions"] - len(state["accepted_questions"]),
            "error": state["last_error"],
        }


def _generate_one_accepted_batch(
    topic: str,
    difficulty: str,
    state: dict,
) -> dict:
    # PL: Ta funkcja robi dokładnie jedną udaną paczkę albo kończy się porażką.
    # EN: This function produces exactly one accepted batch or ends in failure.
    requested_questions = state["requested_questions"]
    accepted_questions = state["accepted_questions"]
    batch_number = state["batch_number"]
    locked_batch_size = state["locked_batch_size"]
    stats = state["stats"]

    remaining_questions = requested_questions - len(accepted_questions)
    accepted_batch = None
    last_reject_reason = None
    last_error_details = None

    primary_batch_size = normalize_batch_size(locked_batch_size, remaining_questions)
    fallback_batch_size = normalize_batch_size(FALLBACK_BATCH_SIZE, remaining_questions)

    attempted_batch_size = primary_batch_size
    attempt_number = 1
    retries_for_size: dict[int, int] = {}
    recent_question_texts = extract_recent_question_texts(state)

    while attempted_batch_size > 0:
        retries_for_size[attempted_batch_size] = retries_for_size.get(attempted_batch_size, 0) + 1
        retry_number_for_this_size = retries_for_size[attempted_batch_size]

        attempt_label = get_attempt_label(
            attempted_batch_size=attempted_batch_size,
            primary_batch_size=primary_batch_size,
            fallback_batch_size=fallback_batch_size,
        )

        print("\n===== BATCH SEARCH =====")
        print(f"batch_number: {batch_number}")
        print(f"attempt_number: {attempt_number}")
        print(f"attempt_label: {attempt_label}")
        print(f"retry_number_for_this_size: {retry_number_for_this_size}")
        print(f"remaining_questions: {remaining_questions}")
        print(f"trying_batch_size: {attempted_batch_size}")
        print(f"locked_batch_size: {locked_batch_size}")

        batch_result = generate_quiz_batch(
            topic=topic,
            difficulty=difficulty,
            num_questions=attempted_batch_size,
            recent_question_texts=recent_question_texts,
        )

        if batch_result["ok"]:
            cross_batch_quality_result = evaluate_cross_batch_quality(
                state=state,
                batch_quiz=batch_result["quiz"],
            )

            if cross_batch_quality_result is None:
                accepted_batch = batch_result
                break

            batch_result = cross_batch_quality_result

        reject_reason = batch_result["reject_reason"]
        error_details = batch_result["error_details"]
        reject_family = classify_reject_family(reject_reason)

        last_reject_reason = reject_reason
        last_error_details = error_details

        stats["rejected_batches"] += 1
        if reject_reason == "rate_limit":
            stats["rate_limit_reject_count"] += 1

        if reject_family == "quality":
            stats["quality_reject_count"] += 1
        elif reject_family == "output":
            stats["output_reject_count"] += 1
        elif reject_family == "other":
            stats["other_reject_count"] += 1

        print("\n===== BATCH REJECTED =====")
        print(f"batch_number: {batch_number}")
        print(f"attempt_number: {attempt_number}")
        print(f"attempt_label: {attempt_label}")
        print(f"requested_in_batch: {attempted_batch_size}")
        print(f"reject_reason: {reject_reason}")
        if error_details:
            print(f"error_details: {error_details}")

        if reject_reason in OUTPUT_REJECT_REASONS:
            print_output_failure_debug(
                topic=topic,
                difficulty=difficulty,
                batch_number=batch_number,
                attempt_label=attempt_label,
                attempted_batch_size=attempted_batch_size,
                locked_batch_size=locked_batch_size,
                reject_reason=reject_reason,
                error_details=error_details,
            )

        # PL: Błędy jakości zwykle próbujemy raz jeszcze w tym samym rozmiarze.
        # PL: Wyjątek: duplicate_questions przy małych batchach (<= 5) od razu redukujemy,
        # PL: bo ponowienie tej samej wielkości często tylko traci czas.
        # EN: Quality errors are usually retried once more at the same batch size.
        # EN: Exception: duplicate_questions for small batches (<= 5) are reduced immediately,
        # EN: because retrying the same size often wastes time.
        should_retry_same_size = (
            reject_reason in QUALITY_REJECT_REASONS
            and retry_number_for_this_size < MAX_RETRIES_PER_BATCH_SIZE
            and not (
                reject_reason == "duplicate_questions"
                and attempted_batch_size <= FALLBACK_BATCH_SIZE
            )
        )

        if should_retry_same_size:
            stats["retry_count"] += 1

            print("\n===== BATCH RETRY SAME SIZE =====")
            print(f"batch_number: {batch_number}")
            print(f"retry_reason: {reject_reason}")
            print(f"retry_same_batch_size: {attempted_batch_size}")

            attempt_number += 1
            continue

        # PL: Długi rate limit albo TPD przerywa dalsze próby od razu.
        # PL: Nie ma sensu robić wielu retry co kilka sekund.
        # EN: A long rate limit or TPD stops further attempts immediately.
        # EN: Repeating retries every few seconds is not useful in that case.
        if reject_reason == "rate_limit" and is_long_rate_limit_wait(error_details):
            print("\n===== RATE LIMIT HALT =====")
            print(f"batch_number: {batch_number}")
            if error_details:
                print(f"error_details: {error_details}")
            break

        # PL: Krótki rate limit 429 zwykle nie oznacza złego batcha.
        # PL: Najpierw czekamy chwilę i próbujemy jeszcze raz tym samym rozmiarem.
        # EN: A short 429 rate limit usually does not mean the batch itself is bad.
        # EN: First we wait briefly and retry with the same batch size.
        if (
            reject_reason == "rate_limit"
            and retry_number_for_this_size < MAX_RATE_LIMIT_RETRIES_PER_BATCH_SIZE
        ):
            wait_seconds = extract_rate_limit_wait_seconds(error_details)
            stats["rate_limit_retry_count"] += 1

            print("\n===== RATE LIMIT WAIT =====")
            print(f"batch_number: {batch_number}")
            print(f"wait_seconds: {wait_seconds:.2f}")
            print(f"retry_same_batch_size_after_wait: {attempted_batch_size}")

            time.sleep(wait_seconds)

            attempt_number += 1
            continue

        # PL: Błędy outputowe sterują głównym fallbackiem 10 -> 5 -> 3.
        # EN: Output errors drive the main fallback path 10 -> 5 -> 3.
        if reject_reason in OUTPUT_REJECT_REASONS:
            if (
                attempted_batch_size == primary_batch_size
                and primary_batch_size > fallback_batch_size
                and fallback_batch_size > 0
            ):
                print("\n===== BATCH FALLBACK =====")
                print(f"batch_number: {batch_number}")
                print(f"fallback_reason: {reject_reason}")
                print(f"fallback_from: {attempted_batch_size}")
                print(f"fallback_to: {fallback_batch_size}")

                if attempted_batch_size == 10 and fallback_batch_size == 5:
                    stats["fallback_10_to_5_count"] += 1

                locked_batch_size = lock_safe_batch_size(
                    current_locked_batch_size=locked_batch_size,
                    new_locked_batch_size=fallback_batch_size,
                    batch_number=batch_number,
                )
                state["locked_batch_size"] = locked_batch_size

                attempted_batch_size = fallback_batch_size
                attempt_number += 1
                continue

            if attempted_batch_size <= FALLBACK_BATCH_SIZE and attempted_batch_size > MIN_SAFE_BATCH_SIZE:
                next_safe_batch_size = normalize_batch_size(
                    attempted_batch_size - OUTPUT_BATCH_STEP_DOWN,
                    remaining_questions,
                )

                if next_safe_batch_size < 1:
                    next_safe_batch_size = 1

                print("\n===== BATCH OUTPUT FALLBACK =====")
                print(f"batch_number: {batch_number}")
                print(f"fallback_reason: {reject_reason}")
                print(f"fallback_from: {attempted_batch_size}")
                print(f"fallback_to: {next_safe_batch_size}")

                if attempted_batch_size == 5 and next_safe_batch_size == 3:
                    stats["fallback_5_to_3_count"] += 1

                locked_batch_size = lock_safe_batch_size(
                    current_locked_batch_size=locked_batch_size,
                    new_locked_batch_size=next_safe_batch_size,
                    batch_number=batch_number,
                )
                state["locked_batch_size"] = locked_batch_size

                attempted_batch_size = next_safe_batch_size
                attempt_number += 1
                continue

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

        if last_error_details:
            print(f"error_details: {last_error_details}")

        state["failed"] = True
        state["last_error"] = (
            last_error_details
            or f"LLM error: could not generate a valid batch ({last_reject_reason or 'unknown'})."
        )

        print_generation_batching_summary(
            topic=topic,
            difficulty=difficulty,
            requested_questions=requested_questions,
            generated_questions=len(accepted_questions),
            locked_batch_size=state["locked_batch_size"],
            stats=stats,
            completed=False,
        )

        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": state,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": remaining_questions,
            "error": state["last_error"],
        }

    batch_quiz = accepted_batch["quiz"]
    batch_questions = batch_quiz.get("questions", [])
    output_tokens = accepted_batch.get("output_tokens")
    returned_questions = accepted_batch.get("returned_questions", len(batch_questions))

    accepted_questions.extend(batch_questions)
    if len(accepted_questions) > requested_questions:
        del accepted_questions[requested_questions:]

    stats["total_batches"] += 1

    if batch_quiz.get("quiz_title"):
        state["final_quiz_title"] = batch_quiz["quiz_title"]

    remaining_questions = requested_questions - len(accepted_questions)

    print("\n===== BATCH ACCEPTED =====")
    print(f"batch_number: {batch_number}")
    print(f"accepted_now: {len(batch_questions)}")
    print(f"accepted_total: {len(accepted_questions)}")
    print(f"remaining_questions: {remaining_questions}")
    print(f"returned_questions: {returned_questions}")
    print(f"output_tokens: {output_tokens}")
    print(f"locked_batch_size_after_accept: {state['locked_batch_size']}")

    state["batch_number"] += 1

    partial_quiz = build_quiz_from_state(state, fallback_title=topic)

    return {
        "ok": True,
        "completed": False,
        "failed": False,
        "state": state,
        "quiz": partial_quiz,
        "new_questions": batch_questions,
        "remaining_questions": remaining_questions,
        "accepted_now": len(batch_questions),
        "accepted_total": len(accepted_questions),
        "output_tokens": output_tokens,
        "returned_questions": returned_questions,
    }


def generate_next_quiz_chunk(
    topic: str,
    difficulty: str,
    state: dict,
) -> dict:
    # PL: Główne API do MVP partial loading.
    # EN: Main API for the partial loading MVP.
    if not isinstance(state, dict):
        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": None,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": 0,
            "error": "generation state must be a dict",
        }

    requested_questions = state.get("requested_questions")
    if not isinstance(requested_questions, int):
        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": state,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": 0,
            "error": "generation state is missing requested_questions",
        }

    if requested_questions < 1 or requested_questions > DEFAULT_BATCH_QUESTION_LIMIT:
        error_message = (
            f"Invalid question count: {requested_questions}. "
            f"Allowed range is 1-{DEFAULT_BATCH_QUESTION_LIMIT}."
        )
        state["failed"] = True
        state["last_error"] = error_message

        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": state,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": 0,
            "error": error_message,
        }

    if state.get("completed"):
        final_quiz = build_quiz_from_state(state, fallback_title=topic)
        return {
            "ok": True,
            "completed": True,
            "failed": False,
            "state": state,
            "quiz": final_quiz,
            "new_questions": [],
            "remaining_questions": 0,
        }

    if state.get("failed"):
        return {
            "ok": False,
            "completed": False,
            "failed": True,
            "state": state,
            "quiz": None,
            "new_questions": [],
            "remaining_questions": requested_questions - len(state.get("accepted_questions", [])),
            "error": state.get("last_error"),
        }

    step_result = _generate_one_accepted_batch(topic, difficulty, state)
    if not step_result["ok"]:
        return step_result

    if len(state["accepted_questions"]) >= requested_questions:
        return finalize_generation_success(topic, difficulty, state)

    return step_result


def start_partial_quiz_generation(
    topic: str,
    difficulty: str,
    num_questions: int,
) -> dict:
    # PL: Wygodny start do UI - tworzy stan i od razu próbuje pobrać pierwszy batch.
    # EN: UI-friendly starter - creates state and immediately tries to fetch the first batch.
    state = create_generation_state(num_questions)
    return generate_next_quiz_chunk(topic, difficulty, state)


def generate_quiz_2(topic: str, difficulty: str, num_questions: int) -> dict | None:
    # PL: Stary tryb pełny zostaje dla kompatybilności.
    # EN: The old full mode stays for compatibility.
    start_result = start_partial_quiz_generation(topic, difficulty, num_questions)
    if not start_result["ok"]:
        return None

    state = start_result["state"]

    while not state["completed"] and not state["failed"]:
        step_result = generate_next_quiz_chunk(topic, difficulty, state)
        if not step_result["ok"]:
            return None

    if state["failed"]:
        return None

    return build_quiz_from_state(state, fallback_title=topic)


if __name__ == "__main__":
    quiz = generate_quiz_2(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5,
    )