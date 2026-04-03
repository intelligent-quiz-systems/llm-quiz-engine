import pytest

from validations.validate_quiz import validate_quiz


def test_validate_quiz_accepts_valid_quiz():
    quiz = {
        "quiz_title": "Python podstawy",
        "questions": [
            {
                "question": "Jakiego typu jest 123?",
                "options": ["int", "str", "list", "dict"],
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is True
    assert error_message is None


def test_validate_quiz_rejects_non_dict_input():
    is_valid, error_message = validate_quiz(["not", "a", "dict"])

    assert is_valid is False
    assert error_message == "Quiz musi być obiektem JSON."


def test_validate_quiz_rejects_missing_quiz_title():
    quiz = {
        "questions": [
            {
                "question": "Pytanie testowe",
                "options": ["A", "B"],
                "correct_index": 0,
            }
        ]
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Brakuje pola 'quiz_title'."


def test_validate_quiz_rejects_empty_quiz_title():
    quiz = {
        "quiz_title": "   ",
        "questions": [
            {
                "question": "Pytanie testowe",
                "options": ["A", "B"],
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pole 'quiz_title' musi być niepustym tekstem."


def test_validate_quiz_rejects_missing_questions():
    quiz = {
        "quiz_title": "Python podstawy",
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Brakuje pola 'questions'."


def test_validate_quiz_rejects_empty_questions_list():
    quiz = {"quiz_title": "Python", "questions": []}

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pole 'questions' musi być niepustą listą."


def test_validate_quiz_rejects_question_that_is_not_dict():
    quiz = {
        "quiz_title": "Python",
        "questions": ["to nie jest pytanie"],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1 musi być obiektem."


@pytest.mark.parametrize(
    "question_data, expected_error",
    [
        (
            {"options": ["A", "B"], "correct_index": 0},
            "Pytanie 1: brakuje pola 'question'.",
        ),
        (
            {"question": "Pytanie?", "correct_index": 0},
            "Pytanie 1: brakuje pola 'options'.",
        ),
        (
            {"question": "Pytanie?", "options": ["A", "B"]},
            "Pytanie 1: brakuje pola 'correct_index'.",
        ),
    ],
)
def test_validate_quiz_rejects_missing_question_fields(question_data, expected_error):
    quiz = {
        "quiz_title": "Python",
        "questions": [question_data],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == expected_error


def test_validate_quiz_rejects_empty_question_text():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "   ",
                "options": ["A", "B"],
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'question' musi być niepustym tekstem."


def test_validate_quiz_rejects_options_that_are_not_list():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Pytanie",
                "options": "A, B, C",
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'options' musi być listą co najmniej 2 odpowiedzi."


def test_validate_quiz_rejects_too_few_options():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Pytanie",
                "options": ["A"],
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'options' musi być listą co najmniej 2 odpowiedzi."


def test_validate_quiz_rejects_non_text_options():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Pytanie",
                "options": ["A", "", "C", "D"],
                "correct_index": 0,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: wszystkie odpowiedzi muszą być niepustym tekstem."


def test_validate_quiz_rejects_non_integer_correct_index():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Która odpowiedź jest poprawna?",
                "options": ["A", "B", "C"],
                "correct_index": "0",
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'correct_index' musi być liczbą całkowitą."


def test_validate_quiz_rejects_negative_correct_index():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Która odpowiedź jest poprawna?",
                "options": ["A", "B", "C"],
                "correct_index": -1,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'correct_index' jest poza zakresem odpowiedzi."


def test_validate_quiz_rejects_correct_index_out_of_range():
    quiz = {
        "quiz_title": "Python",
        "questions": [
            {
                "question": "Która odpowiedź jest poprawna?",
                "options": ["A", "B", "C"],
                "correct_index": 3,
            }
        ],
    }

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pytanie 1: 'correct_index' jest poza zakresem odpowiedzi."