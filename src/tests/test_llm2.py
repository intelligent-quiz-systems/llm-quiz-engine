import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

from pydantic import BaseModel, ValidationError


LLM2_FILE = Path(__file__).resolve().parents[1] / "llm" / "llm2.py"


class FakeQuiz:
    @staticmethod
    def model_validate(data):
        return data


def load_llm2_module(fake_run_prompt, fake_quiz_class=FakeQuiz, module_name="tested_llm2_module"):
    fake_llm_package = ModuleType("llm")
    fake_llm_client_module = ModuleType("llm.llm_client")
    fake_quiz_model_module = ModuleType("llm.quiz_model")

    fake_llm_client_module.run_prompt = fake_run_prompt
    fake_quiz_model_module.Quiz = fake_quiz_class

    sys.modules["llm"] = fake_llm_package
    sys.modules["llm.llm_client"] = fake_llm_client_module
    sys.modules["llm.quiz_model"] = fake_quiz_model_module

    spec = spec_from_file_location(module_name, LLM2_FILE)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    sys.modules.pop(module_name, None)
    spec.loader.exec_module(module)
    return module


def test_generate_quiz_2_returns_quiz_json_on_success():
    fake_response = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Co robi print()?",
                "options": [
                    "Wypisuje tekst",
                    "Usuwa plik",
                    "Tworzy klasę",
                    "Kończy program",
                ],
                "correct_index": 0,
            }
        ],
    }

    fake_run_prompt = Mock(return_value=fake_response)

    llm2_module = load_llm2_module(fake_run_prompt=fake_run_prompt)
    result = llm2_module.generate_quiz_2("Python", "easy", 1)

    assert result == fake_response

    fake_run_prompt.assert_called_once()
    system_prompt, user_prompt, response_model = fake_run_prompt.call_args.args

    assert "You are a quiz generator." in system_prompt
    assert "Return ONLY valid JSON." in system_prompt
    assert "options must contain exactly 4 answers" in system_prompt

    assert "Generate a quiz in Polish." in user_prompt
    assert "Topic: Python" in user_prompt
    assert "Difficulty: easy" in user_prompt
    assert "exactly 1 questions" in user_prompt

    assert response_model.__name__ == "FakeQuiz"


def test_generate_quiz_2_returns_none_on_validation_error():
    fake_run_prompt = Mock(return_value={"invalid": "data"})

    class QuizThatRaisesValidationError:
        @staticmethod
        def model_validate(data):
            raise ValidationError.from_exception_data(
                "Quiz",
                [
                    {
                        "type": "missing",
                        "loc": ("questions",),
                        "msg": "Field required",
                        "input": data,
                    }
                ],
            )

    llm2_module = load_llm2_module(
        fake_run_prompt=fake_run_prompt,
        fake_quiz_class=QuizThatRaisesValidationError,
        module_name="tested_llm2_validation_error",
    )

    result = llm2_module.generate_quiz_2("Python", "medium", 3)

    assert result is None


def test_generate_quiz_2_returns_none_on_llm_error():
    fake_run_prompt = Mock(side_effect=RuntimeError("API error"))

    llm2_module = load_llm2_module(
        fake_run_prompt=fake_run_prompt,
        module_name="tested_llm2_runtime_error",
    )

    result = llm2_module.generate_quiz_2("Docker", "hard", 2)

    assert result is None