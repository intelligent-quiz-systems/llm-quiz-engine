import os
from openai import OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

from llm.generation_config import LLM_MODEL, LLM_TEMPERATURE

load_dotenv()


api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not set in environment")

base_url = os.getenv("GROQ_BASE_URL")
if not base_url:
    raise ValueError("GROQ_BASE_URL not set in environment")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

def run_text_prompt(
    system_prompt: str,
    user_prompt: str,
) -> str | None:
    """Runs an LLM prompt and returns plain text response."""
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=LLM_TEMPERATURE,
    )
    content = response.choices[0].message.content
    return content.strip() if content else None


def run_prompt(
    system_prompt: str,
    user_prompt: str,
    response_model: type[BaseModel],
    include_metadata: bool = False,
) -> dict:
    """
    Runs an LLM prompt using structured output with a Pydantic model.

    When include_metadata=False (default): returns parsed quiz dict directly.
    When include_metadata=True: returns {"quiz": ..., "input_tokens": ...,
        "output_tokens": ..., "reasoning_tokens": ..., "total_tokens": ...,
        "cached_tokens": ..., "model": ..., "response_id": ...}
    """
    response = client.responses.parse(
        model=LLM_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text_format=response_model,
        temperature=LLM_TEMPERATURE,
    )

    parsed_obj = response.output_parsed

    if not include_metadata:
        return parsed_obj.model_dump()

    usage = getattr(response, "usage", None)
    input_details  = getattr(usage, "input_tokens_details",  None) if usage else None
    output_details = getattr(usage, "output_tokens_details", None) if usage else None

    return {
        "quiz":             parsed_obj.model_dump(),
        "input_tokens":     getattr(usage, "input_tokens",  None) if usage else None,
        "output_tokens":    getattr(usage, "output_tokens", None) if usage else None,
        "reasoning_tokens": getattr(output_details, "reasoning_tokens", None) if output_details else None,
        "total_tokens":     getattr(usage, "total_tokens",  None) if usage else None,
        "cached_tokens":    getattr(input_details,  "cached_tokens",    None) if input_details  else None,
        "model":            LLM_MODEL,
        "response_id":      getattr(response, "id", None),
    }