from difflib import SequenceMatcher
from functools import lru_cache

TEXT_SIMILARITY_THRESHOLD = 0.88

# Druga warstwa kontroli: podobieństwo merytoryczne / semantyczne.
# Domyślnie włączona, ale działa bezpiecznie:
# jeśli brakuje zależności, loguje pominięcie zamiast wywalać aplikację.
# Second validation layer: semantic / meaning-based similarity.
# Enabled by default, but designed to fail safely:
# if dependencies are missing, it logs a skip instead of crashing the app.
ENABLE_SEMANTIC_SIMILARITY = True

# "suspicious_only" = najpierw szybki filtr tekstowy, potem embeddingi tylko dla podejrzanych par
# "all_pairs" = embeddingi dla wszystkich par pytań
# "suspicious_only" = first use a fast text filter, then run embeddings only for suspicious pairs
# "all_pairs" = run embeddings for all question pairs
SEMANTIC_CHECK_MODE = "suspicious_only"

# Próg tekstowy do wyłapania par "podejrzanych", które warto sprawdzić semantycznie
# Text threshold used to flag "suspicious" pairs worth checking semantically
SEMANTIC_TEXT_PRECHECK_THRESHOLD = 0.55

# Próg podobieństwa semantycznego
# Semantic similarity threshold
SEMANTIC_SIMILARITY_THRESHOLD = 0.84

# Model wielojęzyczny, sensowny dla pytań po polsku
# Multilingual model suitable for Polish questions
SEMANTIC_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _extract_normalized_questions(quiz_json: dict) -> list[str]:
    questions = quiz_json.get("questions", [])
    return [_normalize_text(q.get("question", "")) for q in questions]


def _iter_question_pairs(normalized_questions: list[str]):
    for i in range(len(normalized_questions)):
        q1 = normalized_questions[i]
        if not q1:
            continue

        for j in range(i + 1, len(normalized_questions)):
            q2 = normalized_questions[j]
            if not q2:
                continue

            yield i, j, q1, q2


@lru_cache(maxsize=1)
def _load_semantic_dependencies():
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity

        return {
            "ok": True,
            "SentenceTransformer": SentenceTransformer,
            "cosine_similarity": cosine_similarity,
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "SentenceTransformer": None,
            "cosine_similarity": None,
            "error": str(e),
        }


@lru_cache(maxsize=1)
def _get_semantic_model():
    deps = _load_semantic_dependencies()
    if not deps["ok"]:
        raise RuntimeError(deps["error"] or "semantic tools are not available")

    SentenceTransformer = deps["SentenceTransformer"]
    return SentenceTransformer(SEMANTIC_MODEL_NAME)


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


def find_similar_questions(
    quiz_json: dict,
    threshold: float = TEXT_SIMILARITY_THRESHOLD,
) -> list[str]:
    issues = []
    normalized_questions = _extract_normalized_questions(quiz_json)

    for i, j, q1, q2 in _iter_question_pairs(normalized_questions):
        score = SequenceMatcher(None, q1, q2).ratio()
        if score >= threshold:
            issues.append(
                f"Very similar questions: Q{i + 1} and Q{j + 1} (score={score:.2f})"
            )

    return issues


def _get_semantic_candidate_pairs(
    normalized_questions: list[str],
    mode: str = SEMANTIC_CHECK_MODE,
    text_precheck_threshold: float = SEMANTIC_TEXT_PRECHECK_THRESHOLD,
) -> list[tuple[int, int, str, str]]:
    pairs = []

    for i, j, q1, q2 in _iter_question_pairs(normalized_questions):
        if mode == "all_pairs":
            pairs.append((i, j, q1, q2))
            continue

        text_score = SequenceMatcher(None, q1, q2).ratio()
        if text_score >= text_precheck_threshold:
            pairs.append((i, j, q1, q2))

    return pairs


def find_semantically_similar_questions(
    quiz_json: dict,
    threshold: float = SEMANTIC_SIMILARITY_THRESHOLD,
    mode: str = SEMANTIC_CHECK_MODE,
) -> tuple[list[str], str | None]:
    if not ENABLE_SEMANTIC_SIMILARITY:
        return [], "semantic similarity disabled"

    deps = _load_semantic_dependencies()
    if not deps["ok"]:
        return [], f"semantic similarity skipped: missing dependency ({deps['error']})"

    normalized_questions = _extract_normalized_questions(quiz_json)
    candidate_pairs = _get_semantic_candidate_pairs(
        normalized_questions,
        mode=mode,
        text_precheck_threshold=SEMANTIC_TEXT_PRECHECK_THRESHOLD,
    )

    if not candidate_pairs:
        return [], None

    unique_texts = {}
    ordered_unique_texts = []

    for _, _, q1, q2 in candidate_pairs:
        if q1 not in unique_texts:
            unique_texts[q1] = len(ordered_unique_texts)
            ordered_unique_texts.append(q1)
        if q2 not in unique_texts:
            unique_texts[q2] = len(ordered_unique_texts)
            ordered_unique_texts.append(q2)

    try:
        model = _get_semantic_model()
    except Exception as e:
        return [], f"semantic similarity skipped: model load failed ({e})"

    cosine_similarity = deps["cosine_similarity"]
    embeddings = model.encode(ordered_unique_texts)

    issues = []
    for i, j, q1, q2 in candidate_pairs:
        idx1 = unique_texts[q1]
        idx2 = unique_texts[q2]

        score = cosine_similarity([embeddings[idx1]], [embeddings[idx2]])[0][0]
        if score >= threshold:
            issues.append(
                f"Semantically similar questions: Q{i + 1} and Q{j + 1} (score={score:.2f})"
            )

    return issues, None


def collect_quiz_quality_issues(quiz_json: dict) -> dict:
    structure_issues = check_question_structure(quiz_json)
    duplicate_questions = find_duplicate_questions(quiz_json)
    similar_questions = find_similar_questions(quiz_json)
    semantic_similar_questions, semantic_note = find_semantically_similar_questions(quiz_json)

    return {
        "structure_issues": structure_issues,
        "duplicate_questions": duplicate_questions,
        "similar_questions": similar_questions,
        "semantic_similar_questions": semantic_similar_questions,
        "semantic_note": semantic_note,
    }


def print_quiz_debug_checks(quiz_json: dict, requested_questions: int | None = None) -> None:
    issues = collect_quiz_quality_issues(quiz_json)

    structure_issues = issues["structure_issues"]
    duplicate_questions = issues["duplicate_questions"]
    similar_questions = issues["similar_questions"]
    semantic_similar_questions = issues["semantic_similar_questions"]
    semantic_note = issues["semantic_note"]

    print("\n===== QUIZ DEBUG CHECKS =====")
    print(
        f"requested_questions: "
        f"{requested_questions if requested_questions is not None else 'N/A'}"
    )
    print(f"structure_issues_count: {len(structure_issues)}")
    print(f"duplicate_questions_count: {len(duplicate_questions)}")
    print(f"similar_questions_count: {len(similar_questions)}")
    print(f"semantic_similar_questions_count: {len(semantic_similar_questions)}")

    if semantic_note:
        print(f"semantic_similarity_note: {semantic_note}")

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

    if semantic_similar_questions:
        print("\n--- SEMANTICALLY SIMILAR QUESTIONS ---")
        for issue in semantic_similar_questions:
            print(issue)