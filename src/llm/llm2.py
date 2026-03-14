import json
import sys
from pathlib import Path
from pydantic import ValidationError

CURRENT_DIR = Path(__file__).resolve().parent      # src/llm
SRC_DIR = CURRENT_DIR.parent                       # src

if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# Support both package import and direct script execution
try:
    from .llm_client import run_prompt
except ImportError:
    from llm_client import run_prompt

try:
    from .quiz_model import Quiz
except ImportError:
    from quiz_model import Quiz

from utils import translate_difficulty_pl_to_en


def generate_quiz_2(topic: str, difficulty: str, num_questions: int) -> str | None:
    system_prompt = (
        "You are a quiz generator. "
        "Generate quiz in JSON format with data strictly matching the schema."
    )

    user_prompt = (
        f"Generate a quiz about {topic} in JSON format in Polish."
        f"Difficulty: {translate_difficulty_pl_to_en(difficulty)}. "
        f"The quiz must contain exactly {num_questions} questions. "
        "Each question must have exactly 4 options "
        "and a correct_index from 0 to 3."
    )

    try:
        quiz_json = run_prompt(system_prompt, user_prompt, Quiz)

        print("\n===== RESULT QUIZ JSON =====")
        print(quiz_json )

        # Validate returned JSON against the Pydantic model
        quiz = Quiz.model_validate(quiz_json)

        formatted_quiz_json = json.dumps(quiz_json, indent=2, ensure_ascii=False) 

        print("\n===== VALIDATED QUIZ JSON =====")
        print(formatted_quiz_json )
        
        return quiz_json

    except ValidationError as e:
        print("Validation error:", e)
        return None

    except Exception as e:
        print("LLM error:", e)
        return None


if __name__ == "__main__":
    quiz = generate_quiz_2(
        topic="Postawy pythona",
        difficulty="Średni",
        num_questions=5
    )