from difflib import SequenceMatcher


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def check_question_structure(quiz_json: dict) -> list[str]:
    issues = []

    questions = quiz_json.get("questions", [])
    if not isinstance(questions, list):
        return ["questions is not a list"]

    for i, q in enumerate(questions):
        prefix = f"Q{i+1}"

        if not isinstance(q, dict):
            issues.append(f"{prefix}: question item is not a dict")
            continue

        question = q.get("question")
        options = q.get("options")
        correct_index = q.get("correct_index")

        if not isinstance(question, str) or not question.strip():
            issues.append(f"{prefix}: question is empty or not a string")

        if not isinstance(options, list):
            issues.append(f"{prefix}: options is not a list")
            continue

        if len(options) != 4:
            issues.append(f"{prefix}: expected 4 options, got {len(options)}")

        normalized_options = []
        for opt in options:
            if not isinstance(opt, str) or not opt.strip():
                issues.append(f"{prefix}: option is empty or not a string")
            else:
                normalized_options.append(_normalize_text(opt))

        if len(normalized_options) != len(set(normalized_options)):
            issues.append(f"{prefix}: duplicate options detected")

        if not isinstance(correct_index, int):
            issues.append(f"{prefix}: correct_index is not int")
        elif not (0 <= correct_index <= 3):
            issues.append(f"{prefix}: correct_index out of range (0-3)")

    return issues


def find_duplicate_questions(quiz_json: dict) -> list[str]:
    issues = []
    seen = {}

    questions = quiz_json.get("questions", [])
    for i, q in enumerate(questions):
        text = _normalize_text(q.get("question", ""))
        if not text:
            continue

        if text in seen:
            issues.append(f"Duplicate question: Q{seen[text] + 1} and Q{i + 1}")
        else:
            seen[text] = i

    return issues


def find_similar_questions(quiz_json: dict, threshold: float = 0.88) -> list[str]:
    issues = []
    questions = quiz_json.get("questions", [])

    normalized_questions = [
        _normalize_text(q.get("question", ""))
        for q in questions
    ]

    for i in range(len(normalized_questions)):
        q1 = normalized_questions[i]
        if not q1:
            continue

        for j in range(i + 1, len(normalized_questions)):
            q2 = normalized_questions[j]
            if not q2:
                continue

            score = SequenceMatcher(None, q1, q2).ratio()
            if score >= threshold:
                issues.append(
                    f"Very similar questions: Q{i + 1} and Q{j + 1} (score={score:.2f})"
                )

    return issues


def print_quiz_debug_checks(quiz_json: dict, requested_questions: int | None = None) -> None:
    structure_issues = check_question_structure(quiz_json)
    duplicate_questions = find_duplicate_questions(quiz_json)
    similar_questions = find_similar_questions(quiz_json)

    print("\n===== QUIZ DEBUG CHECKS =====")
    print(f"requested_questions: {requested_questions if requested_questions is not None else 'N/A'}")
    print(f"structure_issues_count: {len(structure_issues)}")
    print(f"duplicate_questions_count: {len(duplicate_questions)}")
    print(f"similar_questions_count: {len(similar_questions)}")

    if structure_issues:
        print("\n--- STRUCTURE ISSUES ---")
        for issue in structure_issues:
            print(issue)

    if duplicate_questions:
        print("\n--- DUPLICATE QUESTIONS ---")
        for issue in duplicate_questions:
            print(issue)

    if similar_questions:
        print("\n--- VERY SIMILAR QUESTIONS ---")
        for issue in similar_questions:
            print(issue)