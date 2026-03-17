import json
import sys
from pathlib import Path
from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]  # src

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz


def generate_quiz_2(topic: str, difficulty: str, num_questions: int) -> str | None:
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

        Requirements:
        - exactly {num_questions} questions
        - each question must have exactly 4 options
        - correct_index must be between 0 and 3

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