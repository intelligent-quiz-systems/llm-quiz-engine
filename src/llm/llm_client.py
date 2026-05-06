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


def run_prompt(system_prompt: str, user_prompt: str, response_model: type[BaseModel]) -> dict:
    """
    Runs an LLM prompt using structured output with a Pydantic model.
    Returns the result as JSON (dict).
    """

    response = client.responses.parse(
        model=LLM_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text_format=response_model,
        temperature = LLM_TEMPERATURE 
    )

    print("\n===== RAW LLM RESPONSE =====")
    print(response)
    

    parsed_obj = response.output_parsed

    return parsed_obj.model_dump()