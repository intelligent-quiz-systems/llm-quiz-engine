import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not set in environment")

client = Groq(api_key=api_key)

LLM_MODEL = "llama-3.3-70b-versatile"
LLM_TEMPERATURE = 0.7


def run_prompt(system_prompt: str, user_prompt: str, response_model=None) -> dict:
    """
    Prosta wersja używająca oficjalnego klienta Groq.
    """
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content.strip()

        print("\n===== RAW LLM RESPONSE =====")
        print(content)

        try:
            data = json.loads(content)
            return data
        except json.JSONDecodeError:
            print("Błąd: LLM nie zwrócił poprawnego JSON")
            return {}

    except Exception as e:
        print(f"Błąd w run_prompt: {e}")
        return {}