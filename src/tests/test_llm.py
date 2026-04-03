import json
import sys
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

LLM_FILE = Path(__file__).resolve().parents[1] / "llm" / "llm.py"


def load_llm_module(module_name="tested_llm_module"):
    spec = spec_from_file_location(module_name, LLM_FILE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules.pop(module_name, None)
    spec.loader.exec_module(module)
    return module


def build_chat_completion(payload):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )


def make_valid_quiz_response(topic="Python"):
    return {
        "quiz_title": topic,
        "questions": [
            {
                "question": "Co robi funkcja print()?",
                "options": [
                    "Wypisuje tekst na ekran",
                    "Usuwa zmienną",
                    "Tworzy klasę",
                    "Zamyka program",
                ],
                "correct_index": 0,
            }
        ],
    }


def setup_llm_with_fake_client(monkeypatch, payload, module_name="tested_llm_module"):
    fake_client = Mock()
    fake_client.chat.completions.create.return_value = build_chat_completion(payload)

    fake_groq_ctor = Mock(return_value=fake_client)

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("groq.Groq", fake_groq_ctor)

    llm_module = load_llm_module(module_name)
    return llm_module, fake_client, fake_groq_ctor


def test_import_raises_error_when_groq_api_key_is_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("groq.Groq", Mock())

    with pytest.raises(ValueError, match="GROQ_API_KEY not set in environment"):
        load_llm_module("tested_llm_missing_key")


def test_generate_quiz_builds_request_and_returns_parsed_json(monkeypatch):
    fake_response = make_valid_quiz_response("Python")

    llm_module, fake_client, fake_groq_ctor = setup_llm_with_fake_client(
        monkeypatch,
        json.dumps(fake_response, ensure_ascii=False),
        module_name="tested_llm_success",
    )

    result = llm_module.generate_quiz("Python", "Łatwy", 1)

    assert result == fake_response
    fake_groq_ctor.assert_called_once_with(api_key="test-key")

    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-oss-120b"
    assert call_kwargs["temperature"] == 0.7

    assert "messages" in call_kwargs
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"

    prompt = call_kwargs["messages"][0]["content"]
    assert "Python" in prompt
    assert "Difficulty level: easy" in prompt
    assert "Number of questions: 1" in prompt
    assert "Return ONLY valid JSON" in prompt
    assert "all content must be in Polish" in prompt
    assert "questions must stay strictly within the topic: Python" in prompt


@pytest.mark.parametrize(
    "difficulty_input, expected_in_prompt",
    [
        ("Łatwy", "easy"),
        ("Średni", "medium"),
        ("Trudny", "hard"),
        ("expert", "expert"),
    ],
)
def test_generate_quiz_handles_difficulty_values(
    monkeypatch, difficulty_input, expected_in_prompt
):
    fake_response = make_valid_quiz_response("Docker")

    llm_module, fake_client, _ = setup_llm_with_fake_client(
        monkeypatch,
        json.dumps(fake_response, ensure_ascii=False),
        module_name=f"tested_llm_difficulty_{expected_in_prompt}",
    )

    llm_module.generate_quiz("Docker", difficulty_input, 1)

    prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert f"Difficulty level: {expected_in_prompt}" in prompt


@pytest.mark.parametrize("num_questions", [1, 3, 5])
def test_generate_quiz_includes_question_count_in_prompt(monkeypatch, num_questions):
    fake_response = make_valid_quiz_response("Python")

    llm_module, fake_client, _ = setup_llm_with_fake_client(
        monkeypatch,
        json.dumps(fake_response, ensure_ascii=False),
        module_name=f"tested_llm_num_questions_{num_questions}",
    )

    llm_module.generate_quiz("Python", "Łatwy", num_questions)

    prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert f"Number of questions: {num_questions}" in prompt
    assert f"generate exactly {num_questions} questions" in prompt


def test_generate_quiz_returns_parsed_json_for_different_topic(monkeypatch):
    fake_response = {
        "quiz_title": "Docker",
        "questions": [
            {
                "question": "Czym jest obraz Dockera?",
                "options": [
                    "Szablon do tworzenia kontenerów",
                    "Edytor kodu",
                    "System operacyjny",
                    "Baza danych",
                ],
                "correct_index": 0,
            }
        ],
    }

    llm_module, _, _ = setup_llm_with_fake_client(
        monkeypatch,
        json.dumps(fake_response, ensure_ascii=False),
        module_name="tested_llm_docker_topic",
    )

    result = llm_module.generate_quiz("Docker", "Łatwy", 1)

    assert result == fake_response
    assert result["quiz_title"] == "Docker"
    assert isinstance(result["questions"], list)
    assert len(result["questions"]) == 1


def test_generate_quiz_raises_json_decode_error_for_invalid_json(monkeypatch):
    llm_module, _, _ = setup_llm_with_fake_client(
        monkeypatch,
        "To nie jest poprawny JSON",
        module_name="tested_llm_invalid_json",
    )

    with pytest.raises(json.JSONDecodeError):
        llm_module.generate_quiz("Python", "Średni", 3)