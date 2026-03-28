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


def test_validate_quiz_rejects_empty_questions_list():
    quiz = {"quiz_title": "Python", "questions": []}

    is_valid, error_message = validate_quiz(quiz)

    assert is_valid is False
    assert error_message == "Pole 'questions' musi być niepustą listą."


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


def test_validate_quiz_rejects_non_dict_input():
    is_valid, error_message = validate_quiz(["not", "a", "dict"])
    assert is_valid is False
    assert error_message == "Quiz musi być obiektem JSON."