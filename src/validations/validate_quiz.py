def validate_quiz(quiz):
    if not isinstance(quiz, dict):
        return False, "Quiz musi być obiektem JSON."

    if "quiz_title" not in quiz:
        return False, "Brakuje pola 'quiz_title'."

    if not isinstance(quiz["quiz_title"], str) or not quiz["quiz_title"].strip():
        return False, "Pole 'quiz_title' musi być niepustym tekstem."

    if "questions" not in quiz:
        return False, "Brakuje pola 'questions'."

    if not isinstance(quiz["questions"], list) or len(quiz["questions"]) == 0:
        return False, "Pole 'questions' musi być niepustą listą."

    for i, question in enumerate(quiz["questions"], start=1):
        if not isinstance(question, dict):
            return False, f"Pytanie {i} musi być obiektem."

        if "question" not in question:
            return False, f"Pytanie {i}: brakuje pola 'question'."

        if "options" not in question:
            return False, f"Pytanie {i}: brakuje pola 'options'."

        if "correct_index" not in question:
            return False, f"Pytanie {i}: brakuje pola 'correct_index'."

        if not isinstance(question["question"], str) or not question["question"].strip():
            return False, f"Pytanie {i}: 'question' musi być niepustym tekstem."

        if not isinstance(question["options"], list) or len(question["options"]) != 4:
            return False, f"Pytanie {i}: 'options' musi być listą dokładnie 4 odpowiedzi."

        if not all(isinstance(opt, str) and opt.strip() for opt in question["options"]):
            return False, f"Pytanie {i}: wszystkie odpowiedzi muszą być niepustym tekstem."

        if not isinstance(question["correct_index"], int):
            return False, f"Pytanie {i}: 'correct_index' musi być liczbą całkowitą."

        if question["correct_index"] < 0 or question["correct_index"] >= len(question["options"]):
            return False, f"Pytanie {i}: 'correct_index' jest poza zakresem odpowiedzi."

    return True, None