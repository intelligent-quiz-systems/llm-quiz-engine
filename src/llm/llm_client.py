import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from llm.quiz_debug_checks import print_quiz_debug_checks

LLM_MODEL = "openai/gpt-oss-120b"
LLM_TEMPERATURE = 0.7
DEBUG_LLM = True

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


def run_prompt(
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    requested_questions: int | None = None,
    max_output_tokens: int | None = None,
) -> dict:
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
        print(f"system_prompt_chars: {len(system_prompt)}")
        print(f"user_prompt_chars: {len(user_prompt)}")

        print("\n===== TOKEN USAGE =====")
        if usage:
            print(f"input_tokens: {getattr(usage, 'input_tokens', 'N/A')}")
            print(f"output_tokens: {getattr(usage, 'output_tokens', 'N/A')}")
            print(f"total_tokens: {getattr(usage, 'total_tokens', 'N/A')}")

            output_details = getattr(usage, "output_tokens_details", None)
            print(
                f"reasoning_tokens: "
                f"{getattr(output_details, 'reasoning_tokens', 'N/A')}"
            )
        else:
            print("usage not available")

        print("\n===== RESPONSE STATUS =====")
        print(f"status: {response_status}")
        print(f"incomplete_details: {incomplete_details}")
        print(f"max_output_tokens: {getattr(response, 'max_output_tokens', 'N/A')}")
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