import json
import sys
from pathlib import Path
from pydantic import ValidationError

SRC_DIR = Path(__file__).resolve().parents[1]  # src

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from llm.llm_client import run_prompt
from llm.quiz_model import Quiz, TopicFromText

# Import Prompt Managera
from prompt_manager.manager import PromptManager


TOPIC_EXTRACTION_CHARS = 2000
QUIZ_SOURCE_CONTEXT_CHARS = 10000


def extract_topic_from_text(source_text: str) -> str | None:
    if not source_text or not source_text.strip():
        return None

    manager = PromptManager()

    built = manager.build_from_template(
        prompt_name="topic_extraction",
        source_text=source_text[:TOPIC_EXTRACTION_CHARS]
    )

    if not built:
        print("Błąd: nie udało się pobrać promptu topic_extraction")
        return None

    try:
        response_json = run_prompt(built["system"], built["user"], TopicFromText)
        response = TopicFromText.model_validate(response_json)
        topic = response.topic.strip()
        return topic if topic else None
    except Exception:
        return None


def generate_quiz(
    topic: str,
    difficulty: str,
    num_questions: int,
    source_text: str | None = None
) -> dict | None:
    
    manager = PromptManager()

    built = manager.build_from_template(
        prompt_name="quiz_generation",
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        source_text=source_text[:QUIZ_SOURCE_CONTEXT_CHARS] if source_text else "No source text provided.",
        quiz_title=f"Quiz: {topic}"   # ← dodaj tę linię
    )    

    if not built:
        print("Błąd: nie udało się pobrać promptu")
        return None

    try:
        result = run_prompt(built["system"], built["user"], None)

        print("\n===== RAW LLM RESPONSE =====")
        print(result)

        if isinstance(result, str):
            import json
            quiz_data = json.loads(result)
        else:
            quiz_data = result

        # Fallback - dodajemy brakujące pola
        if isinstance(quiz_data, dict):
            if "quiz_title" not in quiz_data:
                quiz_data["quiz_title"] = f"Quiz: {topic}"
            if "questions" not in quiz_data:
                quiz_data["questions"] = []

        return quiz_data

    except Exception as e:
        print("LLM error:", e)
        return None

def generate_hint(
    question: str,
    options: list[str],
    correct_answer: str,
    context: str | None = None,
    hint_level: str = "easy"
) -> str | None:
    """
    Generuje jedną podpowiedź.
    """
    manager = PromptManager()

    built = manager.build_from_template(
        prompt_name="hint_generation",
        question=question,
        options=", ".join(options) if options else "Brak opcji",
        correct_answer=correct_answer,
        context=context if context else "Brak dodatkowego kontekstu źródłowego.",
        hint_level=hint_level
    )

    if not built:
        return "Nie udało się wygenerować podpowiedzi."

    try:
        result = run_prompt(built["system"], built["user"], None)
        
        # Jeśli to dict z kluczem "hint"
        if isinstance(result, dict) and "hint" in result:
            return result["hint"].strip()
        elif isinstance(result, str):
            return result.strip()
        else:
            return str(result)
            
    except Exception as e:
        print(f"Błąd generowania hintu ({hint_level}): {e}")
        return "Nie udało się wygenerować podpowiedzi w tej chwili."