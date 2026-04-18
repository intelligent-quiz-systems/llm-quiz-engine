import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from llm.quiz_debug_checks import print_quiz_debug_checks

LLM_MODEL = "openai/gpt-oss-120b"
LLM_TEMPERATURE = 0.7
DEBUG_LLM = False

# PL: Przełączniki debugowe dla szczegółowych sekcji logów.
# PL: Zostawione w kodzie — włączyć ręcznie gdy potrzebna głębsza diagnostyka.
# EN: Debug toggles for verbose log sections.
# EN: Kept in code — enable manually when deeper diagnostics are needed.
SHOW_RAW_LLM_RESPONSE = False
SHOW_VERBOSE_LLM_REQUEST_DETAILS = False

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not set in environment")

base_url = os.getenv("GROQ_BASE_URL")
if not base_url:
    raise ValueError("GROQ_BASE_URL not set in environment")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
)


def _compact_text(text: str, max_length: int = 400) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length] + "..."


def _extract_provider_error_payload(exc: Exception):
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return body

    response = getattr(exc, "response", None)
    if response is not None:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    return None


def _extract_provider_error_info(exc: Exception) -> dict:
    payload = _extract_provider_error_payload(exc)
    error_obj = None

    if isinstance(payload, dict):
        error_obj = payload.get("error", payload)
        if not isinstance(error_obj, dict):
            error_obj = None

    return {
        "code": error_obj.get("code") if error_obj else None,
        "message": error_obj.get("message") if error_obj else None,
        "failed_generation": error_obj.get("failed_generation") if error_obj else None,
    }


def _format_failed_generation_log(failed_generation) -> str:
    if failed_generation is None:
        return "failed_generation: not available"
    if not str(failed_generation).strip():
        return "failed_generation: not provided by provider"
    return f"failed_generation: {_compact_text(str(failed_generation))}"


def run_prompt(
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    requested_questions: int | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    try:
        response = client.responses.parse(
            model=LLM_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=response_model,
            temperature=LLM_TEMPERATURE,
            max_output_tokens=max_output_tokens,
        )
    except Exception as e:
        provider_error = _extract_provider_error_info(e)
        error_code = provider_error["code"]
        failed_generation = provider_error["failed_generation"]

        if DEBUG_LLM:
            print("\n===== LLM ERROR =====")
            print(f"requested_questions: {requested_questions if requested_questions is not None else 'N/A'}")
            print(f"error_type: {type(e).__name__}")
            print(f"error_code: {error_code if error_code else 'N/A'}")
            print(f"error_message: {str(e)}")

            if error_code == "json_validate_failed":
                print(_format_failed_generation_log(failed_generation))

        error_message = str(e)
        if error_code == "json_validate_failed":
            error_message = f"{error_message} | {_format_failed_generation_log(failed_generation)}"

        raise ValueError(error_message) from e

    parsed_obj = response.output_parsed

    response_status = getattr(response, "status", None)
    incomplete_details = getattr(response, "incomplete_details", None)

    usage = getattr(response, "usage", None)
    output_tokens = getattr(usage, "output_tokens", None) if usage else None

    if response_status == "incomplete":
        raise ValueError(f"LLM response incomplete: {incomplete_details}")

    if DEBUG_LLM:
        print("\n===== REQUEST INFO =====")
        print(
            f"requested_questions: "
            f"{requested_questions if requested_questions is not None else 'N/A'}"
        )

        if SHOW_VERBOSE_LLM_REQUEST_DETAILS:
            print(f"system_prompt_chars: {len(system_prompt)}")
            print(f"user_prompt_chars: {len(user_prompt)}")

        print("\n===== TOKEN USAGE =====")
        if usage:
            print(f"output_tokens: {getattr(usage, 'output_tokens', 'N/A')}")

            output_details = getattr(usage, "output_tokens_details", None)
            print(
                f"reasoning_tokens: "
                f"{getattr(output_details, 'reasoning_tokens', 'N/A')}"
            )

            if SHOW_VERBOSE_LLM_REQUEST_DETAILS:
                print(f"input_tokens: {getattr(usage, 'input_tokens', 'N/A')}")
                print(f"total_tokens: {getattr(usage, 'total_tokens', 'N/A')}")
        else:
            print("usage not available")

        print("\n===== RESPONSE STATUS =====")
        print(f"status: {response_status}")
        print(f"incomplete_details: {incomplete_details}")
        print(f"max_output_tokens: {getattr(response, 'max_output_tokens', 'N/A')}")

        if SHOW_VERBOSE_LLM_REQUEST_DETAILS:
            print(f"service_tier: {getattr(response, 'service_tier', 'N/A')}")

            raw_text = ""
            output_items = getattr(response, "output", []) or []
            for item in output_items:
                content_items = getattr(item, "content", []) or []
                for content in content_items:
                    text = getattr(content, "text", None)
                    if text:
                        raw_text += text

            print("\n===== OUTPUT SIZE =====")
            print(f"raw_text_chars: {len(raw_text)}")

        print("\n===== QUESTION COUNT =====")
        if parsed_obj is not None:
            questions = getattr(parsed_obj, "questions", []) or []
            returned_questions = len(questions)

            print(
                f"requested_questions: "
                f"{requested_questions if requested_questions is not None else 'N/A'}"
            )
            print(f"returned_questions: {returned_questions}")

            if requested_questions is not None:
                print(f"question_delta: {returned_questions - requested_questions}")

            print_quiz_debug_checks(
                parsed_obj.model_dump(),
                requested_questions=requested_questions,
            )
        else:
            print(
                f"requested_questions: "
                f"{requested_questions if requested_questions is not None else 'N/A'}"
            )
            print("returned_questions: N/A (parsed_obj is None)")

        if SHOW_RAW_LLM_RESPONSE:
            print("\n===== RAW LLM RESPONSE =====")
            print(response)

    if parsed_obj is None:
        raise ValueError("LLM returned no parsed output")

    return {
        "quiz": parsed_obj.model_dump(),
        "output_tokens": output_tokens,
        "status": response_status,
        "incomplete_details": incomplete_details,
    }