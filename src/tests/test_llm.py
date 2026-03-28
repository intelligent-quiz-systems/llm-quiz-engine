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


def test_import_raises_error_when_groq_api_key_is_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("groq.Groq", Mock())

    with pytest.raises(ValueError, match="GROQ_API_KEY not set in environment"):
        load_llm_module("tested_llm_missing_key")


def test_generate_quiz_builds_prompt_and_returns_parsed_json(monkeypatch):
    fake_response = {
        "quiz_title": "Python",
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

    fake_client = Mock()
    fake_client.chat.completions.create.return_value = build_chat_completion(
        json.dumps(fake_response, ensure_ascii=False)
    )

    fake_groq_ctor = Mock(return_value=fake_client)

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("groq.Groq", fake_groq_ctor)

    llm_module = load_llm_module("tested_llm_success")
    result = llm_module.generate_quiz("Python", "Łatwy", 1)

    assert result == fake_response
    fake_groq_ctor.assert_called_once_with(api_key="test-key")

    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-oss-120b"
    assert call_kwargs["temperature"] == 0.7
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"

    prompt = call_kwargs["messages"][0]["content"]
    assert "Generate a quiz in Polish about: Python" in prompt
    assert "Difficulty level: easy" in prompt
    assert "Number of questions: 1" in prompt
    assert "generate exactly 1 questions" in prompt
    assert "questions must stay strictly within the topic: Python" in prompt


def test_generate_quiz_keeps_unknown_difficulty_value(monkeypatch):
    fake_client = Mock()
    fake_client.chat.completions.create.return_value = build_chat_completion(
        json.dumps(
            {
                "quiz_title": "Docker",
                "questions": [
                    {
                        "question": "Czym jest obraz Dockera?",
                        "options": ["A", "B", "C", "D"],
                        "correct_index": 0,
                    }
                ],
            }
        )
    )

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("groq.Groq", Mock(return_value=fake_client))

    llm_module = load_llm_module("tested_llm_unknown_difficulty")
    llm_module.generate_quiz("Docker", "expert", 1)

    prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Difficulty level: expert" in prompt


def test_generate_quiz_raises_json_decode_error_for_invalid_json(monkeypatch):
    fake_client = Mock()
    fake_client.chat.completions.create.return_value = build_chat_completion(
        "To nie jest poprawny JSON"
    )

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("groq.Groq", Mock(return_value=fake_client))

    llm_module = load_llm_module("tested_llm_invalid_json")

    with pytest.raises(json.JSONDecodeError):
        llm_module.generate_quiz("Python", "Średni", 3)