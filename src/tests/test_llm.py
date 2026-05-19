"""
Tests for the llm.py orchestration layer.

generate_quiz() is a thin orchestrator: it creates state, delegates to
run_batched_generation, validates the result, and logs.  Tests here verify
the orchestration contracts, not the internals of batch strategy or prompts.

Prompt content and batch behaviour are tested in test_batch_strategy.py.
"""
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

LLM_FILE = Path(__file__).resolve().parents[1] / "llm" / "llm.py"


# ── Fake model classes ────────────────────────────────────────────────────────

class FakeQuiz:
    @staticmethod
    def model_validate(data):
        return data


class FakeTopicFromText:
    @staticmethod
    def model_validate(data):
        topic = data.get("topic", "") if isinstance(data, dict) else ""
        return type("TopicResult", (), {"topic": topic})()


# ── Quiz fixtures ─────────────────────────────────────────────────────────────

def make_valid_quiz_response(topic="Python"):
    return {
        "quiz_title": topic,
        "questions": [
            {
                "question": "Co robi print()?",
                "options": ["Wypisuje tekst", "Usuwa plik", "Tworzy klasę", "Kończy program"],
                "correct_index": 0,
            }
        ],
    }


def make_valid_quiz_response_with_n_questions(n, topic="Python"):
    return {
        "quiz_title": topic,
        "questions": [
            {
                "question": f"Pytanie {i + 1}?",
                "options": ["Odpowiedź A", "Odpowiedź B", "Odpowiedź C", "Odpowiedź D"],
                "correct_index": 0,
            }
            for i in range(n)
        ],
    }


# ── Module loader ─────────────────────────────────────────────────────────────

def load_llm_module(
    mock_run_batched,
    fake_quiz_class=FakeQuiz,
    fake_run_prompt=None,
    module_name="tested_llm",
):
    """
    Load llm.py with all its dependencies mocked.

    mock_run_batched replaces run_batched_generation — the batch layer is fully
    mocked here because its behaviour is tested in test_batch_strategy.py.
    """
    fake_run_prompt = fake_run_prompt or Mock()

    # Minimal GenerationState dict that format_state_summary can consume
    def _create_state(topic, difficulty, num_questions, initial_batch_size):
        return {
            "topic": topic,
            "difficulty": difficulty,
            "requested_questions": num_questions,
            "accepted_questions": 0,
            "total_batches": 0,
            "rejected_attempts": 0,
            "initial_batch_size": initial_batch_size,
            "final_locked_batch_size": initial_batch_size,
            "batch_log": [],
            "rejection_log": [],
        }

    # Fake modules
    pkg_llm       = ModuleType("llm")
    mod_client    = ModuleType("llm.llm_client")
    mod_model     = ModuleType("llm.quiz_model")
    mod_batch     = ModuleType("llm.batch_strategy")
    mod_state     = ModuleType("llm.generation_state")
    mod_config    = ModuleType("llm.generation_config")
    # Mocks for modules imported by llm.py when other PRs are merged:
    # diagnostics/provider-error-details, guardrail-prompt-builder, answer-shuffling
    mod_provider  = ModuleType("llm.provider_errors")
    mod_guardrail = ModuleType("llm.guardrail")
    mod_shuffle   = ModuleType("llm.answer_shuffle")
    mod_quality   = ModuleType("llm.question_quality")
    mod_pm_pkg    = ModuleType("prompt_manager")
    mod_pm        = ModuleType("prompt_manager.manager")

    mod_client.run_prompt                    = fake_run_prompt
    mod_model.Quiz                           = fake_quiz_class
    mod_model.TopicFromText                  = FakeTopicFromText
    mod_batch.run_batched_generation         = mock_run_batched
    mod_state.create_state                   = Mock(side_effect=_create_state)
    mod_state.format_state_summary           = Mock(return_value="")
    mod_config.TOPIC_EXTRACTION_CHARS        = 2000
    mod_config.QUIZ_SOURCE_CONTEXT_CHARS     = 10000
    mod_config.INITIAL_BATCH_SIZE            = 10
    mod_config.FALLBACK_BATCH_SIZE           = 5
    mod_config.MIN_BATCH_SIZE                = 1
    mod_config.MAX_ATTEMPTS_PER_BATCH_SIZE   = 2
    mod_config.GUARDRAIL_MAX_QUESTIONS       = 10
    mod_config.SIMILAR_QUESTION_THRESHOLD    = 0.7
    mod_provider.classify_provider_error     = Mock(return_value={})
    mod_provider.format_error_log            = Mock(return_value="")
    mod_guardrail.build_guardrail_context    = Mock(return_value={"text": "", "question_count": 0, "chars": 0})
    mod_guardrail.extract_question_texts     = Mock(return_value=[])
    mod_guardrail.format_guardrail_log       = Mock(return_value="")
    mod_shuffle.shuffle_quiz_options         = Mock(side_effect=lambda q: q)
    mod_shuffle.shuffle_quiz_options_balanced = Mock(side_effect=lambda q: q)
    mod_quality.run_quality_checks           = Mock(return_value=[])
    mod_quality.format_quality_log           = Mock(return_value="")

    # PromptManager used only by extract_topic_from_text
    fake_pm_instance = Mock()
    fake_pm_instance.build_from_template.return_value = {
        "system": "You are a topic extraction assistant.",
        "user": "Extract the main topic from this text:\n\n{source_text}\n\nReturn ONLY JSON.",
    }
    mod_pm.PromptManager = Mock(return_value=fake_pm_instance)

    for key, mod in [
        ("llm", pkg_llm), ("llm.llm_client", mod_client), ("llm.quiz_model", mod_model),
        ("llm.batch_strategy", mod_batch), ("llm.generation_state", mod_state),
        ("llm.generation_config", mod_config),
        ("llm.provider_errors", mod_provider),
        ("llm.guardrail", mod_guardrail),
        ("llm.answer_shuffle", mod_shuffle),
        ("llm.question_quality", mod_quality),
        ("prompt_manager", mod_pm_pkg), ("prompt_manager.manager", mod_pm),
    ]:
        sys.modules[key] = mod

    spec = spec_from_file_location(module_name, LLM_FILE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules.pop(module_name, None)
    spec.loader.exec_module(module)
    return module


# ── generate_quiz — return value contracts ────────────────────────────────────

def test_generate_quiz_returns_quiz_json_on_success():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name="t_success")
    result = llm.generate_quiz("Python", "easy", 1)
    assert result == quiz


def test_generate_quiz_returns_none_when_batch_returns_none():
    mock_batch = Mock(return_value=None)
    llm = load_llm_module(mock_batch, module_name="t_none")
    assert llm.generate_quiz("Python", "easy", 5) is None


def test_generate_quiz_returns_none_on_validation_error():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)

    class QuizThatFails:
        @staticmethod
        def model_validate(data):
            raise ValidationError.from_exception_data(
                "Quiz",
                [{"type": "missing", "loc": ("questions",),
                  "msg": "Field required", "input": data}],
            )

    llm = load_llm_module(mock_batch, fake_quiz_class=QuizThatFails,
                          module_name="t_validation_error")
    assert llm.generate_quiz("Python", "medium", 3) is None


def test_generate_quiz_returns_none_when_batch_raises():
    mock_batch = Mock(side_effect=RuntimeError("API error"))
    llm = load_llm_module(mock_batch, module_name="t_batch_raises")
    assert llm.generate_quiz("Docker", "hard", 2) is None


# ── generate_quiz — orchestration delegation ──────────────────────────────────

def test_generate_quiz_calls_run_batched_with_correct_args():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name="t_batch_args")
    llm.generate_quiz("Python", "easy", 5, source_text="some context")

    mock_batch.assert_called_once()
    args, kwargs = mock_batch.call_args
    assert args[0] == "Python"
    assert args[1] == "easy"
    assert args[2] == 5
    assert args[3] == "some context"


def test_generate_quiz_calls_create_state():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name="t_create_state")
    llm.generate_quiz("Python", "easy", 10)
    # get the create_state mock from the loaded module's generation_state
    assert sys.modules["llm.generation_state"].create_state.called


def test_generate_quiz_passes_state_to_run_batched():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name="t_state_passed")
    llm.generate_quiz("Python", "easy", 5)
    _, kwargs = mock_batch.call_args
    assert "state" in kwargs
    assert kwargs["state"] is not None


def test_generate_quiz_calls_balanced_shuffle():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name="t_shuffle_called")
    llm.generate_quiz("Python", "easy", 1)
    assert sys.modules["llm.answer_shuffle"].shuffle_quiz_options_balanced.called


def test_generate_quiz_validates_result_with_quiz_model():
    quiz = make_valid_quiz_response("Python")
    mock_batch = Mock(return_value=quiz)

    class TrackingQuiz:
        called_with = None
        @staticmethod
        def model_validate(data):
            TrackingQuiz.called_with = data
            return data

    llm = load_llm_module(mock_batch, fake_quiz_class=TrackingQuiz,
                          module_name="t_validation_called")
    result = llm.generate_quiz("Python", "easy", 1)
    assert result == quiz
    assert TrackingQuiz.called_with == quiz


# ── generate_quiz — various inputs ───────────────────────────────────────────

@pytest.mark.parametrize("topic,difficulty,n", [
    ("Python", "easy", 1),
    ("Docker", "medium", 5),
    ("SQL", "hard", 20),
])
def test_generate_quiz_returns_dict_for_various_inputs(topic, difficulty, n):
    quiz = make_valid_quiz_response_with_n_questions(n, topic)
    mock_batch = Mock(return_value=quiz)
    llm = load_llm_module(mock_batch, module_name=f"t_inputs_{topic}_{n}")
    result = llm.generate_quiz(topic, difficulty, n)
    assert isinstance(result, dict)
    assert len(result["questions"]) == n


# ── extract_topic_from_text ───────────────────────────────────────────────────

def test_extract_topic_from_text_returns_topic():
    fake_run_prompt = Mock(return_value={"topic": "Programowanie w Pythonie"})
    mock_batch = Mock(return_value=None)
    llm = load_llm_module(mock_batch, fake_run_prompt=fake_run_prompt,
                          module_name="t_extract_topic")
    topic = llm.extract_topic_from_text("Python to język programowania.")
    assert topic == "Programowanie w Pythonie"


def test_extract_topic_from_text_returns_none_for_empty_input():
    mock_batch = Mock(return_value=None)
    llm = load_llm_module(mock_batch, module_name="t_extract_empty")
    assert llm.extract_topic_from_text("") is None
    assert llm.extract_topic_from_text("   ") is None
